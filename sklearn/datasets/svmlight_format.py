"""This module implements a loader and dumper for the svmlight format

This format is a text-based format, with one sample per line. It does
not store zero valued features hence is suitable for sparse dataset.

The first element of each line can be used to store a target variable to
predict.

This format is used as the default format for both svmlight and the
libsvm command line programs.
"""

# Authors: Mathieu Blondel <mathieu@mblondel.org>
#          Lars Buitinck <L.J.Buitinck@uva.nl>
#          Olivier Grisel <olivier.grisel@ensta.org>
# License: Simple BSD.

import numpy as np
import scipy.sparse as sp
from ._svmlight_format import _load_svmlight_file


def load_svmlight_file(f, n_features=None, dtype=np.float64,
                       multilabel=False, zero_based="auto"):
    """Load datasets in the svmlight / libsvm format into sparse CSR matrix

    This format is a text-based format, with one sample per line. It does
    not store zero valued features hence is suitable for sparse dataset.

    The first element of each line can be used to store a target variable
    to predict.

    This format is used as the default format for both svmlight and the
    libsvm command line programs.

    Parsing a text based source can be expensive. When working on
    repeatedly on the same dataset, it is recommended to wrap this
    loader with joblib.Memory.cache to store a memmapped backup of the
    CSR results of the first call and benefit from the near instantaneous
    loading of memmapped structures for the subsequent calls.

    This implementation is naive: it does allocate too much memory and
    is slow since written in python. On large datasets it is recommended
    to use an optimized loader such as:

      https://github.com/mblondel/svmlight-loader

    Parameters
    ----------
    f: str or file-like open in binary mode.
        (Path to) a file to load.

    n_features: int or None
        The number of features to use. If None, it will be inferred. This
        argument is useful to load several files that are subsets of a
        bigger sliced dataset: each subset might not have example of
        every feature, hence the inferred shape might vary from one
        slice to another.

    multilabel: boolean, optional
        Samples may have several labels each (see
        http://www.csie.ntu.edu.tw/~cjlin/libsvmtools/datasets/multilabel.html)

    zero_based: boolean or "auto", optional
        Whether column indices in f are zero-based (True) or one-based
        (False). If set to "auto", a heuristic check is applied to determine
        this from the file contents. Both kinds of files occur "in the wild",
        but they are unfortunately not self-identifying. Using "auto" or True
        should always be safe.

    Returns
    -------
    (X, y)

    where X is a scipy.sparse matrix of shape (n_samples, n_features),
          y is a ndarray of shape (n_samples,), or, in the multilabel case,
          a list of tuples of length n_samples.

    See also
    --------
    load_svmlight_files: similar function for loading multiple files in this
    format, enforcing the same number of features/columns on all of them.
    """
    return tuple(load_svmlight_files([f], n_features, dtype, multilabel,
                                     zero_based))


def _open_and_load(f, dtype, multilabel, zero_based):
    if hasattr(f, "read"):
        return _load_svmlight_file(f, dtype, multilabel, zero_based)
    with open(f, "rb") as f:
        return _load_svmlight_file(f, dtype, multilabel, zero_based)


def load_svmlight_files(files, n_features=None, dtype=np.float64,
                        multilabel=False, zero_based="auto"):
    """Load dataset from multiple files in SVMlight format

    This function is equivalent to mapping load_svmlight_file over a list of
    files, except that the results are concatenated into a single, flat list
    and the samples vectors are constrained to all have the same number of
    features.

    Parameters
    ----------
    files : iterable over {str, file-like}
        (Paths to) files to load.

    n_features: int or None
        The number of features to use. If None, it will be inferred from the
        maximum column index occurring in any of the files.

    multilabel: boolean, optional
        Samples may have several labels each (see
        http://www.csie.ntu.edu.tw/~cjlin/libsvmtools/datasets/multilabel.html)

    zero_based: boolean or "auto", optional
        Whether column indices in files are zero-based (True) or one-based
        (False). If set to "auto", a heuristic check is applied to determine
        this from the files' contents. Both kinds of files occur "in the wild",
        but they are unfortunately not self-identifying. Using "auto" or True
        should always be safe.

    Returns
    -------
    [X1, y1, ..., Xn, yn]

    where each (Xi, yi) pair is the result from load_svmlight_file(files[i]).

    Rationale
    ---------
    When fitting a model to a matrix X_train and evaluating it against a
    matrix X_test, it is essential that X_train and X_test have the same
    number of features (X_train.shape[1] == X_test.shape[1]). This may not
    be the case if you load the files individually with load_svmlight_file.

    See also
    --------
    load_svmlight_file
    """
    r = [_open_and_load(f, dtype, multilabel, bool(zero_based)) for f in files]

    if zero_based is False \
     or zero_based == "auto" and all(np.min(indices) > 0
                                     for _, indices, _, _ in r):
        for _, indices, _, _ in r:
            indices -= 1

    if n_features is None:
        n_features = max(indices.max() for _, indices, _, _ in r) + 1

    result = []
    for data, indices, indptr, y in r:
        shape = (indptr.shape[0] - 1, n_features)
        result += sp.csr_matrix((data, indices, indptr), shape), y

    return result


def _dump_svmlight(X, y, f, zero_based):
    if X.shape[0] != y.shape[0]:
        raise ValueError("X.shape[0] and y.shape[0] should be the same, "
                         "got: %r and %r instead." % (X.shape[0], y.shape[0]))

    is_sp = int(hasattr(X, "tocsr"))

    one_based = not zero_based
    for i in xrange(X.shape[0]):
        s = u" ".join([u"%d:%f" % (j + one_based, X[i, j])
                       for j in X[i].nonzero()[is_sp]])
        f.write((u"%f %s\n" % (y[i], s)).encode('ascii'))


def dump_svmlight_file(X, y, f, zero_based=True):
    """Dump the dataset in svmlight / libsvm file format.

    This format is a text-based format, with one sample per line. It does
    not store zero valued features hence is suitable for sparse dataset.

    The first element of each line can be used to store a target variable
    to predict.

    Parameters
    ----------
    X : {array-like, sparse matrix}, shape = [n_samples, n_features]
        Training vectors, where n_samples is the number of samples and
        n_features is the number of features.

    y : array-like, shape = [n_samples]
        Target values.

    f : str or file-like in binary mode
        If string it specifies the path that will contain the data.
        If f is a file-like then data will be written to f.

    zero_based : boolean, optional
        Whether column indices should be written zero-based (True) or one-based
        (False).
    """
    if hasattr(f, "write"):
        _dump_svmlight(X, y, f, zero_based)
    else:
        with open(f, "wb") as f:
            _dump_svmlight(X, y, f, zero_based)
