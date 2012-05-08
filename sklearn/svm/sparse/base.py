import numpy as np
import scipy.sparse

from ..base import BaseLibSVM


class SparseBaseLibSVM(BaseLibSVM):
    def __init__(self, impl, kernel, degree, gamma, coef0,
                 tol, C, nu, epsilon, shrinking, probability, cache_size,
                 class_weight, verbose):

        assert kernel in self._sparse_kernels, \
               "kernel should be one of %s, "\
               "%s was given." % (self._kernel_types, kernel)

        super(SparseBaseLibSVM, self).__init__(impl, kernel, degree, gamma,
                coef0, tol, C, nu, epsilon, shrinking, probability, cache_size,
                True, class_weight, verbose)

    def fit(self, X, y, sample_weight=None):
        X = scipy.sparse.csr_matrix(X, dtype=np.float64)
        return super(SparseBaseLibSVM, self).fit(X, y, sample_weight)
