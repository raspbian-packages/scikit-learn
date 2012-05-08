"""Hierarchical Agglomerative Clustering

These routines perform some hierachical agglomerative clustering of some
input data. Currently, only Ward's algorithm is implemented.

Authors : Vincent Michel, Bertrand Thirion, Alexandre Gramfort,
          Gael Varoquaux
License: BSD 3 clause
"""
from heapq import heapify, heappop, heappush, heappushpop
import itertools
import warnings

import numpy as np
from scipy import sparse
from scipy.cluster import hierarchy

from ..base import BaseEstimator
from ..utils._csgraph import cs_graph_components
from ..externals.joblib import Memory
from ..metrics import euclidean_distances

from . import _hierarchical
from ._feature_agglomeration import AgglomerationTransform


###############################################################################
# Ward's algorithm

def ward_tree(X, connectivity=None, n_components=None, copy=True):
    """Ward clustering based on a Feature matrix.

    The inertia matrix uses a Heapq-based representation.

    This is the structured version, that takes into account a some topological
    structure between samples.

    Parameters
    ----------
    X : array of shape (n_samples, n_features)
        feature matrix  representing n_samples samples to be clustered

    connectivity : sparse matrix.
        connectivity matrix. Defines for each sample the neigbhoring samples
        following a given structure of the data. The matrix is assumed to
        be symmetric and only the upper triangular half is used.
        Default is None, i.e, the Ward algorithm is unstructured.

    n_components : int (optional)
        Number of connected components. If None the number of connected
        components is estimated from the connectivity matrix.

    copy : bool (optional)
        Make a copy of connectivity or work inplace. If connectivity
        is not of LIL type there will be a copy in any case.

    Returns
    -------
    children : list of pairs. Lenght of n_nodes
               list of the children of each nodes.
               Leaves of the tree have empty list of children.

    n_components : sparse matrix.
        The number of connected components in the graph.

    n_leaves : int
        The number of leaves in the tree
    """
    X = np.asarray(X)
    n_samples, n_features = X.shape
    if X.ndim == 1:
        X = np.reshape(X, (-1, 1))

    # Compute the number of nodes
    if connectivity is not None:
        if n_components is None:
            n_components, labels = cs_graph_components(connectivity)
        if n_components > 1:
            warnings.warn("the number of connected components of the"
            " connectivity matrix is %d > 1. Completing it to avoid"
            " stopping the tree early."
            % n_components)
            if copy:
                connectivity = connectivity.copy()
                copy = False
            connectivity = _fix_connectivity(X, connectivity,
                                            n_components, labels)
            n_components = 1
    else:
        out = hierarchy.ward(X)
        children_ = out[:, :2].astype(np.int)
        return children_, 1, n_samples

    n_nodes = 2 * n_samples - n_components

    if (connectivity.shape[0] != n_samples or
        connectivity.shape[1] != n_samples):
        raise ValueError('Wrong shape for connectivity matrix: %s '
                         'when X is %s' % (connectivity.shape, X.shape))
    # convert connectivity matrix to LIL eventually with a copy
    if sparse.isspmatrix_lil(connectivity) and copy:
        connectivity = connectivity.copy()
    else:
        connectivity = connectivity.tolil()

    # Remove diagonal from connectivity matrix
    connectivity.setdiag(np.zeros(connectivity.shape[0]))

    # create inertia matrix
    coord_row = []
    coord_col = []
    A = []
    for ind, row in enumerate(connectivity.rows):
        A.append(row)
        # We keep only the upper triangular for the moments
        # Generator expressions are faster than arrays on the following
        row = [i for i in row if i < ind]
        coord_row.extend(len(row) * [ind, ])
        coord_col.extend(row)

    coord_row = np.array(coord_row, dtype=np.int)
    coord_col = np.array(coord_col, dtype=np.int)

    # build moments as a list
    moments_1 = np.zeros(n_nodes)
    moments_1[:n_samples] = 1
    moments_2 = np.zeros((n_nodes, n_features))
    moments_2[:n_samples] = X
    inertia = np.empty(len(coord_row), dtype=np.float)
    _hierarchical.compute_ward_dist(moments_1, moments_2,
                             coord_row, coord_col, inertia)
    inertia = zip(inertia, coord_row, coord_col)
    heapify(inertia)

    # prepare the main fields
    parent = np.arange(n_nodes, dtype=np.int)
    heights = np.zeros(n_nodes)
    used_node = np.ones(n_nodes, dtype=bool)
    children = []

    visited = np.empty(n_nodes, dtype=bool)

    # recursive merge loop
    for k in xrange(n_samples, n_nodes):
        # identify the merge
        while True:
            inert, i, j = heappop(inertia)
            if used_node[i] and used_node[j]:
                break
        parent[i], parent[j], heights[k] = k, k, inert
        children.append([i, j])
        used_node[i] = used_node[j] = False

        # update the moments
        moments_1[k] = moments_1[i] + moments_1[j]
        moments_2[k] = moments_2[i] + moments_2[j]

        # update the structure matrix A and the inertia matrix
        coord_col = []
        visited[:] = False
        visited[k] = True
        for l in set(A[i]).union(A[j]):
            l = _hierarchical._get_parent(l, parent)
            if not visited[l]:
                visited[l] = True
                coord_col.append(l)
                A[l].append(k)
        A.append(coord_col)
        coord_col = np.array(coord_col, dtype=np.int)
        coord_row = np.empty_like(coord_col)
        coord_row.fill(k)
        ini = np.empty(len(coord_row), dtype=np.float)

        _hierarchical.compute_ward_dist(moments_1, moments_2,
                                   coord_row, coord_col, ini)
        for tupl in itertools.izip(ini, coord_row, coord_col):
            heappush(inertia, tupl)

    # Separate leaves in children (empty lists up to now)
    n_leaves = n_samples
    children = np.array(children)  # return numpy array for efficient caching

    return children, n_components, n_leaves


###############################################################################
# For non fully-connected graphs

def _fix_connectivity(X, connectivity, n_components, labels):
    """
    Warning: modifies connectivity in place
    """
    for i in range(n_components):
        idx_i = np.where(labels == i)[0]
        Xi = X[idx_i]
        for j in range(i):
            idx_j = np.where(labels == j)[0]
            Xj = X[idx_j]
            D = euclidean_distances(Xi, Xj)
            ii, jj = np.where(D == np.min(D))
            ii = ii[0]
            jj = jj[0]
            connectivity[idx_i[ii], idx_j[jj]] = True
            connectivity[idx_j[jj], idx_i[ii]] = True
    return connectivity

###############################################################################
# Functions for cutting  hierarchical clustering tree


def _hc_cut(n_clusters, children, n_leaves):
    """Function cutting the ward tree for a given number of clusters.

    Parameters
    ----------
    n_clusters : int or ndarray
        The number of clusters to form.

    children : list of pairs. Length of n_nodes
        List of the children of each nodes.
        Leaves have empty list of children and are not stored.

    n_leaves : int
        Number of leaves of the tree.

    Returns
    -------
    labels : array [n_points]
        cluster labels for each point

    """
    if n_clusters > n_leaves:
        raise ValueError('Cannot extract more clusters than samples: '
            '%s clusters where given for a tree with %s leaves.'
            % (n_clusters, n_leaves))
    # In this function, we store nodes as a heap to avoid recomputing
    # the max of the nodes: the first element is always the smallest
    # We use negated indices as heaps work on smallest elements, and we
    # are interested in largest elements
    # children[-1] is the root of the tree
    nodes = [-(max(children[-1]) + 1)]
    for i in range(n_clusters - 1):
        # As we have a heap, nodes[0] is the smallest element
        these_children = children[-nodes[0] - n_leaves]
        # Insert the 2 children and remove the largest node
        heappush(nodes, -these_children[0])
        heappushpop(nodes, -these_children[1])
    label = np.zeros(n_leaves, dtype=np.int)
    for i, node in enumerate(nodes):
        label[_hierarchical._hc_get_descendent(-node,
                                children, n_leaves)] = i
    return label


###############################################################################
# Class for Ward hierarchical clustering

class Ward(BaseEstimator):
    """Ward hierarchical clustering: constructs a tree and cuts it.

    Parameters
    ----------
    n_clusters : int or ndarray
        The number of clusters to find.

    connectivity : sparse matrix.
        Connectivity matrix. Defines for each sample the neigbhoring
        samples following a given structure of the data.
        Default is None, i.e, the hiearchical clustering algorithm is
        unstructured.

    memory : Instance of joblib.Memory or string
        Used to cache the output of the computation of the tree.
        By default, no caching is done. If a string is given, it is the
        path to the caching directory.

    copy : bool
        Copy the connectivity matrix or work inplace.

    n_components : int (optional)
        The number of connected components in the graph defined by the \
        connectivity matrix. If not set, it is estimated.

    Attributes
    ----------
    `children_` : array-like, shape = [n_nodes, 2]
        List of the children of each nodes.  Leaves of the tree do not appear.

    `labels_` : array [n_points]
        cluster labels for each point

    `n_leaves_` : int
        Number of leaves in the hiearchical tree.

    """

    def __init__(self, n_clusters=2, memory=Memory(cachedir=None, verbose=0),
                 connectivity=None, copy=True, n_components=None):
        self.n_clusters = n_clusters
        self.memory = memory
        self.copy = copy
        self.n_components = n_components
        self.connectivity = connectivity

    def fit(self, X):
        """Fit the hierarchical clustering on the data

        Parameters
        ----------
        X : array-like, shape = [n_samples, n_features]
            The samples a.k.a. observations.

        Returns
        -------
        self
        """
        memory = self.memory
        if isinstance(memory, basestring):
            memory = Memory(cachedir=memory)

        if not self.connectivity is None:
            if not sparse.issparse(self.connectivity):
                raise TypeError("`connectivity` should be a sparse matrix or "
                        "None, got: %r" % type(self.connectivity))

            if (self.connectivity.shape[0] != X.shape[0] or
                    self.connectivity.shape[1] != X.shape[0]):
                raise ValueError("`connectivity` does not have shape "
                        "(n_samples, n_samples)")

        # Construct the tree
        self.children_, self.n_components, self.n_leaves_ = \
                memory.cache(ward_tree)(X, self.connectivity,
                                n_components=self.n_components, copy=self.copy)

        # Cut the tree
        self.labels_ = _hc_cut(self.n_clusters, self.children_, self.n_leaves_)
        return self


###############################################################################
# Ward-based feature agglomeration

class WardAgglomeration(AgglomerationTransform, Ward):
    """Feature agglomeration based on Ward hierarchical clustering

    Parameters
    ----------
    n_clusters : int or ndarray
        The number of clusters.

    connectivity : sparse matrix
        connectivity matrix. Defines for each feature the neigbhoring
        features following a given structure of the data.
        Default is None, i.e, the hiearchical agglomeration algorithm is
        unstructured.

    memory : Instance of joblib.Memory or string
        Used to cache the output of the computation of the tree.
        By default, no caching is done. If a string is given, it is the
        path to the caching directory.

    copy : bool
        Copy the connectivity matrix or work inplace.

    n_components : int (optional)
        The number of connected components in the graph defined by the
        connectivity matrix. If not set, it is estimated.

    Attributes
    ----------
    `children_` : array-like, shape = [n_nodes, 2]
        List of the children of each nodes.
        Leaves of the tree do not appear.

    `labels_` : array [n_points]
        cluster labels for each point

    `n_leaves_` : int
        Number of leaves in the hiearchical tree.

    """

    def fit(self, X, y=None, **params):
        """Fit the hierarchical clustering on the data

        Parameters
        ----------
        X : array-like, shape = [n_samples, n_features]
            The data

        Returns
        -------
        self
        """
        return Ward.fit(self, X.T, **params)
