# Author: Alexandre Gramfort <alexandre.gramfort@inria.fr>
#         Fabian Pedregosa <fabian.pedregosa@inria.fr>
#         Olivier Grisel <olivier.grisel@ensta.org>
#         Alexis Mignon <alexis.mignon@gmail.com>
#         Manoj Kumar <manojkumarsivaraj334@gmail.com>
#
# License: BSD 3 clause

from libc.math cimport fabs
cimport numpy as np
import numpy as np
import numpy.linalg as linalg

cimport cython
from cpython cimport bool
from cython cimport floating
import warnings

ctypedef np.float64_t DOUBLE
ctypedef np.uint32_t UINT32_t
ctypedef floating (*DOT)(int N, floating *X, int incX, floating *Y,
                         int incY) nogil
ctypedef void (*AXPY)(int N, floating alpha, floating *X, int incX,
                      floating *Y, int incY) nogil
ctypedef floating (*ASUM)(int N, floating *X, int incX) nogil

np.import_array()

# The following two functions are shamelessly copied from the tree code.

cdef enum:
    # Max value for our rand_r replacement (near the bottom).
    # We don't use RAND_MAX because it's different across platforms and
    # particularly tiny on Windows/MSVC.
    RAND_R_MAX = 0x7FFFFFFF


cdef inline UINT32_t our_rand_r(UINT32_t* seed) nogil:
    seed[0] ^= <UINT32_t>(seed[0] << 13)
    seed[0] ^= <UINT32_t>(seed[0] >> 17)
    seed[0] ^= <UINT32_t>(seed[0] << 5)

    return seed[0] % (<UINT32_t>RAND_R_MAX + 1)


cdef inline UINT32_t rand_int(UINT32_t end, UINT32_t* random_state) nogil:
    """Generate a random integer in [0; end)."""
    return our_rand_r(random_state) % end


cdef inline floating fmax(floating x, floating y) nogil:
    if x > y:
        return x
    return y


cdef inline floating fsign(floating f) nogil:
    if f == 0:
        return 0
    elif f > 0:
        return 1.0
    else:
        return -1.0


cdef floating abs_max(int n, floating* a) nogil:
    """np.max(np.abs(a))"""
    cdef int i
    cdef floating m = fabs(a[0])
    cdef floating d
    for i in range(1, n):
        d = fabs(a[i])
        if d > m:
            m = d
    return m


cdef floating max(int n, floating* a) nogil:
    """np.max(a)"""
    cdef int i
    cdef floating m = a[0]
    cdef floating d
    for i in range(1, n):
        d = a[i]
        if d > m:
            m = d
    return m


cdef floating diff_abs_max(int n, floating* a, floating* b) nogil:
    """np.max(np.abs(a - b))"""
    cdef int i
    cdef floating m = fabs(a[0] - b[0])
    cdef floating d
    for i in range(1, n):
        d = fabs(a[i] - b[i])
        if d > m:
            m = d
    return m


cdef extern from "cblas.h":
    enum CBLAS_ORDER:
        CblasRowMajor=101
        CblasColMajor=102
    enum CBLAS_TRANSPOSE:
        CblasNoTrans=111
        CblasTrans=112
        CblasConjTrans=113
        AtlasConj=114

    void daxpy "cblas_daxpy"(int N, double alpha, double *X, int incX,
                             double *Y, int incY) nogil
    void saxpy "cblas_saxpy"(int N, float alpha, float *X, int incX,
                             float *Y, int incY) nogil
    double ddot "cblas_ddot"(int N, double *X, int incX, double *Y, int incY
                             ) nogil
    float sdot "cblas_sdot"(int N, float *X, int incX, float *Y,
                            int incY) nogil
    double dasum "cblas_dasum"(int N, double *X, int incX) nogil
    float sasum "cblas_sasum"(int N, float *X, int incX) nogil
    void dger "cblas_dger"(CBLAS_ORDER Order, int M, int N, double alpha,
                           double *X, int incX, double *Y, int incY,
                           double *A, int lda) nogil
    void dgemv "cblas_dgemv"(CBLAS_ORDER Order, CBLAS_TRANSPOSE TransA,
                             int M, int N, double alpha, double *A, int lda,
                             double *X, int incX, double beta,
                             double *Y, int incY) nogil
    double dnrm2 "cblas_dnrm2"(int N, double *X, int incX) nogil
    void dcopy "cblas_dcopy"(int N, double *X, int incX, double *Y,
                             int incY) nogil
    void dscal "cblas_dscal"(int N, double alpha, double *X, int incX) nogil


@cython.boundscheck(False)
@cython.wraparound(False)
@cython.cdivision(True)
def enet_coordinate_descent(np.ndarray[floating, ndim=1] w,
                            floating alpha, floating beta,
                            np.ndarray[floating, ndim=2, mode='fortran'] X,
                            np.ndarray[floating, ndim=1, mode='c'] y,
                            int max_iter, floating tol,
                            object rng, bint random=0, bint positive=0):
    """Cython version of the coordinate descent algorithm
        for Elastic-Net regression

        We minimize

        (1/2) * norm(y - X w, 2)^2 + alpha norm(w, 1) + (beta/2) norm(w, 2)^2

    """

    # fused types version of BLAS functions
    cdef DOT dot
    cdef AXPY axpy
    cdef ASUM asum

    if floating is float:
        dtype = np.float32
        dot = sdot
        axpy = saxpy
        asum = sasum
    else:
        dtype = np.float64
        dot = ddot
        axpy = daxpy
        asum = dasum

    # get the data information into easy vars
    cdef unsigned int n_samples = X.shape[0]
    cdef unsigned int n_features = X.shape[1]

    # get the number of tasks indirectly, using strides
    cdef unsigned int n_tasks = y.strides[0] / sizeof(floating)

    # compute norms of the columns of X
    cdef np.ndarray[floating, ndim=1] norm_cols_X = (X**2).sum(axis=0)

    # initial value of the residuals
    cdef np.ndarray[floating, ndim=1] R = np.empty(n_samples, dtype=dtype)
    cdef np.ndarray[floating, ndim=1] XtA = np.empty(n_features, dtype=dtype)

    cdef floating tmp
    cdef floating w_ii
    cdef floating d_w_max
    cdef floating w_max
    cdef floating d_w_ii
    cdef floating gap = tol + 1.0
    cdef floating d_w_tol = tol
    cdef floating dual_norm_XtA
    cdef floating R_norm2
    cdef floating w_norm2
    cdef floating l1_norm
    cdef floating const
    cdef floating A_norm2
    cdef unsigned int ii
    cdef unsigned int i
    cdef unsigned int n_iter = 0
    cdef unsigned int f_iter
    cdef UINT32_t rand_r_state_seed = rng.randint(0, RAND_R_MAX)
    cdef UINT32_t* rand_r_state = &rand_r_state_seed

    cdef floating *X_data = <floating*> X.data
    cdef floating *y_data = <floating*> y.data
    cdef floating *w_data = <floating*> w.data
    cdef floating *R_data = <floating*> R.data
    cdef floating *XtA_data = <floating*> XtA.data

    if alpha == 0:
        warnings.warn("Coordinate descent with alpha=0 may lead to unexpected"
            " results and is discouraged.")

    with nogil:
        # R = y - np.dot(X, w)
        for i in range(n_samples):
            R[i] = y[i] - dot(n_features, &X_data[i], n_samples, w_data, 1)

        # tol *= np.dot(y, y)
        tol *= dot(n_samples, y_data, n_tasks, y_data, n_tasks)

        for n_iter in range(max_iter):
            w_max = 0.0
            d_w_max = 0.0
            for f_iter in range(n_features):  # Loop over coordinates
                if random:
                    ii = rand_int(n_features, rand_r_state)
                else:
                    ii = f_iter

                if norm_cols_X[ii] == 0.0:
                    continue

                w_ii = w[ii]  # Store previous value

                if w_ii != 0.0:
                    # R += w_ii * X[:,ii]
                    axpy(n_samples, w_ii, &X_data[ii * n_samples], 1,
                         R_data, 1)

                # tmp = (X[:,ii]*R).sum()
                tmp = dot(n_samples, &X_data[ii * n_samples], 1, R_data, 1)

                if positive and tmp < 0:
                    w[ii] = 0.0
                else:
                    w[ii] = (fsign(tmp) * fmax(fabs(tmp) - alpha, 0)
                             / (norm_cols_X[ii] + beta))

                if w[ii] != 0.0:
                    # R -=  w[ii] * X[:,ii] # Update residual
                    axpy(n_samples, -w[ii], &X_data[ii * n_samples], 1,
                         R_data, 1)

                # update the maximum absolute coefficient update
                d_w_ii = fabs(w[ii] - w_ii)
                if d_w_ii > d_w_max:
                    d_w_max = d_w_ii

                if fabs(w[ii]) > w_max:
                    w_max = fabs(w[ii])

            if (w_max == 0.0 or
                d_w_max / w_max < d_w_tol or
                n_iter == max_iter - 1):
                # the biggest coordinate update of this iteration was smaller
                # than the tolerance: check the duality gap as ultimate
                # stopping criterion

                # XtA = np.dot(X.T, R) - beta * w
                for i in range(n_features):
                    XtA[i] = dot(n_samples, &X_data[i * n_samples],
                                 1, R_data, 1) - beta * w[i]

                if positive:
                    dual_norm_XtA = max(n_features, XtA_data)
                else:
                    dual_norm_XtA = abs_max(n_features, XtA_data)

                # R_norm2 = np.dot(R, R)
                R_norm2 = dot(n_samples, R_data, 1, R_data, 1)

                # w_norm2 = np.dot(w, w)
                w_norm2 = dot(n_features, w_data, 1, w_data, 1)

                if (dual_norm_XtA > alpha):
                    const = alpha / dual_norm_XtA
                    A_norm2 = R_norm2 * (const ** 2)
                    gap = 0.5 * (R_norm2 + A_norm2)
                else:
                    const = 1.0
                    gap = R_norm2

                l1_norm = asum(n_features, w_data, 1)

                # np.dot(R.T, y)
                gap += (alpha * l1_norm
                        - const * dot(n_samples, R_data, 1, y_data, n_tasks)
                        + 0.5 * beta * (1 + const ** 2) * (w_norm2))

                if gap < tol:
                    # return if we reached desired tolerance
                    break
    return w, gap, tol, n_iter + 1


@cython.boundscheck(False)
@cython.wraparound(False)
@cython.cdivision(True)
def sparse_enet_coordinate_descent(floating [:] w,
                            floating alpha, floating beta,
                            np.ndarray[floating, ndim=1, mode='c'] X_data,
                            np.ndarray[int, ndim=1, mode='c'] X_indices,
                            np.ndarray[int, ndim=1, mode='c'] X_indptr,
                            np.ndarray[floating, ndim=1] y,
                            floating[:] X_mean, int max_iter,
                            floating tol, object rng, bint random=0,
                            bint positive=0):
    """Cython version of the coordinate descent algorithm for Elastic-Net

    We minimize:

        (1/2) * norm(y - X w, 2)^2 + alpha norm(w, 1) + (beta/2) * norm(w, 2)^2

    """

    # get the data information into easy vars
    cdef unsigned int n_samples = y.shape[0]
    cdef unsigned int n_features = w.shape[0]

    # compute norms of the columns of X
    cdef unsigned int ii
    cdef floating[:] norm_cols_X

    cdef unsigned int startptr = X_indptr[0]
    cdef unsigned int endptr

    # get the number of tasks indirectly, using strides
    cdef unsigned int n_tasks

    # initial value of the residuals
    cdef floating[:] R = y.copy()

    cdef floating[:] X_T_R
    cdef floating[:] XtA

    # fused types version of BLAS functions
    cdef DOT dot
    cdef ASUM asum

    if floating is float:
        dtype = np.float32
        n_tasks = y.strides[0] / sizeof(float)
        dot = sdot
        asum = sasum
    else:
        dtype = np.float64
        n_tasks = y.strides[0] / sizeof(DOUBLE)
        dot = ddot
        asum = dasum

    norm_cols_X = np.zeros(n_features, dtype=dtype)
    X_T_R = np.zeros(n_features, dtype=dtype)
    XtA = np.zeros(n_features, dtype=dtype)

    cdef floating tmp
    cdef floating w_ii
    cdef floating d_w_max
    cdef floating w_max
    cdef floating d_w_ii
    cdef floating X_mean_ii
    cdef floating R_sum = 0.0
    cdef floating R_norm2
    cdef floating w_norm2
    cdef floating A_norm2
    cdef floating l1_norm
    cdef floating normalize_sum
    cdef floating gap = tol + 1.0
    cdef floating d_w_tol = tol
    cdef floating dual_norm_XtA
    cdef unsigned int jj
    cdef unsigned int n_iter = 0
    cdef unsigned int f_iter
    cdef UINT32_t rand_r_state_seed = rng.randint(0, RAND_R_MAX)
    cdef UINT32_t* rand_r_state = &rand_r_state_seed
    cdef bint center = False

    with nogil:
        # center = (X_mean != 0).any()
        for ii in range(n_features):
            if X_mean[ii]:
                center = True
                break

        for ii in range(n_features):
            X_mean_ii = X_mean[ii]
            endptr = X_indptr[ii + 1]
            normalize_sum = 0.0
            w_ii = w[ii]

            for jj in range(startptr, endptr):
                normalize_sum += (X_data[jj] - X_mean_ii) ** 2
                R[X_indices[jj]] -= X_data[jj] * w_ii
            norm_cols_X[ii] = normalize_sum + \
                (n_samples - endptr + startptr) * X_mean_ii ** 2

            if center:
                for jj in range(n_samples):
                    R[jj] += X_mean_ii * w_ii
            startptr = endptr

        # tol *= np.dot(y, y)
        tol *= dot(n_samples, &y[0], 1, &y[0], 1)

        for n_iter in range(max_iter):

            w_max = 0.0
            d_w_max = 0.0

            for f_iter in range(n_features):  # Loop over coordinates
                if random:
                    ii = rand_int(n_features, rand_r_state)
                else:
                    ii = f_iter

                if norm_cols_X[ii] == 0.0:
                    continue

                startptr = X_indptr[ii]
                endptr = X_indptr[ii + 1]
                w_ii = w[ii]  # Store previous value
                X_mean_ii = X_mean[ii]

                if w_ii != 0.0:
                    # R += w_ii * X[:,ii]
                    for jj in range(startptr, endptr):
                        R[X_indices[jj]] += X_data[jj] * w_ii
                    if center:
                        for jj in range(n_samples):
                            R[jj] -= X_mean_ii * w_ii

                # tmp = (X[:,ii] * R).sum()
                tmp = 0.0
                for jj in range(startptr, endptr):
                    tmp += R[X_indices[jj]] * X_data[jj]

                if center:
                    R_sum = 0.0
                    for jj in range(n_samples):
                        R_sum += R[jj]
                    tmp -= R_sum * X_mean_ii

                if positive and tmp < 0.0:
                    w[ii] = 0.0
                else:
                    w[ii] = fsign(tmp) * fmax(fabs(tmp) - alpha, 0) \
                            / (norm_cols_X[ii] + beta)

                if w[ii] != 0.0:
                    # R -=  w[ii] * X[:,ii] # Update residual
                    for jj in range(startptr, endptr):
                        R[X_indices[jj]] -= X_data[jj] * w[ii]

                    if center:
                        for jj in range(n_samples):
                            R[jj] += X_mean_ii * w[ii]

                # update the maximum absolute coefficient update
                d_w_ii = fabs(w[ii] - w_ii)
                if d_w_ii > d_w_max:
                    d_w_max = d_w_ii

                if w[ii] > w_max:
                    w_max = w[ii]
            if w_max == 0.0 or d_w_max / w_max < d_w_tol or n_iter == max_iter - 1:
                # the biggest coordinate update of this iteration was smaller than
                # the tolerance: check the duality gap as ultimate stopping
                # criterion

                # sparse X.T / dense R dot product
                if center:
                    R_sum = 0.0
                    for jj in range(n_samples):
                        R_sum += R[jj]

                for ii in range(n_features):
                    X_T_R[ii] = 0.0
                    for jj in range(X_indptr[ii], X_indptr[ii + 1]):
                        X_T_R[ii] += X_data[jj] * R[X_indices[jj]]

                    if center:
                        X_T_R[ii] -= X_mean[ii] * R_sum
                    XtA[ii] = X_T_R[ii] - beta * w[ii]

                if positive:
                    dual_norm_XtA = max(n_features, &XtA[0])
                else:
                    dual_norm_XtA = abs_max(n_features, &XtA[0])

                # R_norm2 = np.dot(R, R)
                R_norm2 = dot(n_samples, &R[0], 1, &R[0], 1)

                # w_norm2 = np.dot(w, w)
                w_norm2 = dot(n_features, &w[0], 1, &w[0], 1)
                if (dual_norm_XtA > alpha):
                    const = alpha / dual_norm_XtA
                    A_norm2 = R_norm2 * const**2
                    gap = 0.5 * (R_norm2 + A_norm2)
                else:
                    const = 1.0
                    gap = R_norm2

                l1_norm = asum(n_features, &w[0], 1)

                gap += (alpha * l1_norm - const * dot(
                            n_samples,
                            &R[0], 1,
                            &y[0], n_tasks
                            )
                        + 0.5 * beta * (1 + const ** 2) * w_norm2)

                if gap < tol:
                    # return if we reached desired tolerance
                    break

    return w, gap, tol, n_iter + 1


@cython.boundscheck(False)
@cython.wraparound(False)
@cython.cdivision(True)
def enet_coordinate_descent_gram(floating[:] w, floating alpha, floating beta,
                                 np.ndarray[floating, ndim=2, mode='c'] Q,
                                 np.ndarray[floating, ndim=1, mode='c'] q,
                                 np.ndarray[floating, ndim=1] y,
                                 int max_iter, floating tol, object rng,
                                 bint random=0, bint positive=0):
    """Cython version of the coordinate descent algorithm
        for Elastic-Net regression

        We minimize

        (1/2) * w^T Q w - q^T w + alpha norm(w, 1) + (beta/2) * norm(w, 2)^2

        which amount to the Elastic-Net problem when:
        Q = X^T X (Gram matrix)
        q = X^T y
    """

    # fused types version of BLAS functions
    cdef DOT dot
    cdef AXPY axpy
    cdef ASUM asum

    if floating is float:
        dtype = np.float32
        dot = sdot
        axpy = saxpy
        asum = sasum
    else:
        dtype = np.float64
        dot = ddot
        axpy = daxpy
        asum = dasum

    # get the data information into easy vars
    cdef unsigned int n_samples = y.shape[0]
    cdef unsigned int n_features = Q.shape[0]

    # initial value "Q w" which will be kept of up to date in the iterations
    cdef floating[:] H = np.dot(Q, w)

    cdef floating[:] XtA = np.zeros(n_features, dtype=dtype)
    cdef floating tmp
    cdef floating w_ii
    cdef floating d_w_max
    cdef floating w_max
    cdef floating d_w_ii
    cdef floating q_dot_w
    cdef floating w_norm2
    cdef floating gap = tol + 1.0
    cdef floating d_w_tol = tol
    cdef floating dual_norm_XtA
    cdef unsigned int ii
    cdef unsigned int n_iter = 0
    cdef unsigned int f_iter
    cdef UINT32_t rand_r_state_seed = rng.randint(0, RAND_R_MAX)
    cdef UINT32_t* rand_r_state = &rand_r_state_seed

    cdef floating y_norm2 = np.dot(y, y)
    cdef floating* w_ptr = <floating*>&w[0]
    cdef floating* Q_ptr = &Q[0, 0]
    cdef floating* q_ptr = <floating*>q.data
    cdef floating* H_ptr = &H[0]
    cdef floating* XtA_ptr = &XtA[0]
    tol = tol * y_norm2

    if alpha == 0:
        warnings.warn("Coordinate descent with alpha=0 may lead to unexpected"
            " results and is discouraged.")

    with nogil:
        for n_iter in range(max_iter):
            w_max = 0.0
            d_w_max = 0.0
            for f_iter in range(n_features):  # Loop over coordinates
                if random:
                    ii = rand_int(n_features, rand_r_state)
                else:
                    ii = f_iter

                if Q[ii, ii] == 0.0:
                    continue

                w_ii = w[ii]  # Store previous value

                if w_ii != 0.0:
                    # H -= w_ii * Q[ii]
                    axpy(n_features, -w_ii, Q_ptr + ii * n_features, 1,
                         H_ptr, 1)

                tmp = q[ii] - H[ii]

                if positive and tmp < 0:
                    w[ii] = 0.0
                else:
                    w[ii] = fsign(tmp) * fmax(fabs(tmp) - alpha, 0) \
                        / (Q[ii, ii] + beta)

                if w[ii] != 0.0:
                    # H +=  w[ii] * Q[ii] # Update H = X.T X w
                    axpy(n_features, w[ii], Q_ptr + ii * n_features, 1,
                         H_ptr, 1)

                # update the maximum absolute coefficient update
                d_w_ii = fabs(w[ii] - w_ii)
                if d_w_ii > d_w_max:
                    d_w_max = d_w_ii

                if fabs(w[ii]) > w_max:
                    w_max = fabs(w[ii])

            if w_max == 0.0 or d_w_max / w_max < d_w_tol or n_iter == max_iter - 1:
                # the biggest coordinate update of this iteration was smaller than
                # the tolerance: check the duality gap as ultimate stopping
                # criterion

                # q_dot_w = np.dot(w, q)
                q_dot_w = dot(n_features, w_ptr, 1, q_ptr, 1)

                for ii in range(n_features):
                    XtA[ii] = q[ii] - H[ii] - beta * w[ii]
                if positive:
                    dual_norm_XtA = max(n_features, XtA_ptr)
                else:
                    dual_norm_XtA = abs_max(n_features, XtA_ptr)

                # temp = np.sum(w * H)
                tmp = 0.0
                for ii in range(n_features):
                    tmp += w[ii] * H[ii]
                R_norm2 = y_norm2 + tmp - 2.0 * q_dot_w

                # w_norm2 = np.dot(w, w)
                w_norm2 = dot(n_features, &w[0], 1, &w[0], 1)

                if (dual_norm_XtA > alpha):
                    const = alpha / dual_norm_XtA
                    A_norm2 = R_norm2 * (const ** 2)
                    gap = 0.5 * (R_norm2 + A_norm2)
                else:
                    const = 1.0
                    gap = R_norm2

                # The call to dasum is equivalent to the L1 norm of w
                gap += (alpha * asum(n_features, &w[0], 1) -
                        const * y_norm2 +  const * q_dot_w +
                        0.5 * beta * (1 + const ** 2) * w_norm2)

                if gap < tol:
                    # return if we reached desired tolerance
                    break

    return np.asarray(w), gap, tol, n_iter + 1


@cython.boundscheck(False)
@cython.wraparound(False)
@cython.cdivision(True)
def enet_coordinate_descent_multi_task(double[::1, :] W, double l1_reg,
                                       double l2_reg,
                                       np.ndarray[double, ndim=2, mode='fortran'] X,
                                       np.ndarray[double, ndim=2] Y,
                                       int max_iter, double tol, object rng,
                                       bint random=0):
    """Cython version of the coordinate descent algorithm
        for Elastic-Net mult-task regression

        We minimize

        (1/2) * norm(y - X w, 2)^2 + l1_reg ||w||_21 + (1/2) * l2_reg norm(w, 2)^2

    """
    # get the data information into easy vars
    cdef unsigned int n_samples = X.shape[0]
    cdef unsigned int n_features = X.shape[1]
    cdef unsigned int n_tasks = Y.shape[1]

    # to store XtA
    cdef double[:, ::1] XtA = np.zeros((n_features, n_tasks))
    cdef double XtA_axis1norm
    cdef double dual_norm_XtA

    # initial value of the residuals
    cdef double[:, ::1] R = np.zeros((n_samples, n_tasks))

    cdef double[:] norm_cols_X = np.zeros(n_features)
    cdef double[::1] tmp = np.zeros(n_tasks, dtype=np.float)
    cdef double[:] w_ii = np.zeros(n_tasks, dtype=np.float)
    cdef double d_w_max
    cdef double w_max
    cdef double d_w_ii
    cdef double nn
    cdef double W_ii_abs_max
    cdef double gap = tol + 1.0
    cdef double d_w_tol = tol
    cdef double ry_sum
    cdef double l21_norm
    cdef unsigned int ii
    cdef unsigned int jj
    cdef unsigned int n_iter = 0
    cdef unsigned int f_iter
    cdef UINT32_t rand_r_state_seed = rng.randint(0, RAND_R_MAX)
    cdef UINT32_t* rand_r_state = &rand_r_state_seed

    cdef double* X_ptr = &X[0, 0]
    cdef double* W_ptr = &W[0, 0]
    cdef double* Y_ptr = &Y[0, 0]
    cdef double* wii_ptr = &w_ii[0]

    if l1_reg == 0:
        warnings.warn("Coordinate descent with l1_reg=0 may lead to unexpected"
            " results and is discouraged.")

    with nogil:
        # norm_cols_X = (np.asarray(X) ** 2).sum(axis=0)
        for ii in range(n_features):
            for jj in range(n_samples):
                norm_cols_X[ii] += X[jj, ii] ** 2

        # R = Y - np.dot(X, W.T)
        for ii in range(n_samples):
            for jj in range(n_tasks):
                R[ii, jj] = Y[ii, jj] - (
                    ddot(n_features, X_ptr + ii, n_samples, W_ptr + jj, n_tasks)
                    )

        # tol = tol * linalg.norm(Y, ord='fro') ** 2
        tol = tol * dnrm2(n_samples * n_tasks, Y_ptr, 1) ** 2

        for n_iter in range(max_iter):
            w_max = 0.0
            d_w_max = 0.0
            for f_iter in range(n_features):  # Loop over coordinates
                if random:
                    ii = rand_int(n_features, rand_r_state)
                else:
                    ii = f_iter

                if norm_cols_X[ii] == 0.0:
                    continue

                # w_ii = W[:, ii] # Store previous value
                dcopy(n_tasks, W_ptr + ii * n_tasks, 1, wii_ptr, 1)

                # if np.sum(w_ii ** 2) != 0.0:  # can do better
                if dnrm2(n_tasks, wii_ptr, 1) != 0.0:
                    # R += np.dot(X[:, ii][:, None], w_ii[None, :]) # rank 1 update
                    dger(CblasRowMajor, n_samples, n_tasks, 1.0,
                         X_ptr + ii * n_samples, 1,
                         wii_ptr, 1, &R[0, 0], n_tasks)

                # tmp = np.dot(X[:, ii][None, :], R).ravel()
                dgemv(CblasRowMajor, CblasTrans,
                      n_samples, n_tasks, 1.0, &R[0, 0], n_tasks,
                      X_ptr + ii * n_samples, 1, 0.0, &tmp[0], 1)

                # nn = sqrt(np.sum(tmp ** 2))
                nn = dnrm2(n_tasks, &tmp[0], 1)

                # W[:, ii] = tmp * fmax(1. - l1_reg / nn, 0) / (norm_cols_X[ii] + l2_reg)
                dcopy(n_tasks, &tmp[0], 1, W_ptr + ii * n_tasks, 1)
                dscal(n_tasks, fmax(1. - l1_reg / nn, 0) / (norm_cols_X[ii] + l2_reg),
                          W_ptr + ii * n_tasks, 1)

                # if np.sum(W[:, ii] ** 2) != 0.0:  # can do better
                if dnrm2(n_tasks, W_ptr + ii * n_tasks, 1) != 0.0:
                    # R -= np.dot(X[:, ii][:, None], W[:, ii][None, :])
                    # Update residual : rank 1 update
                    dger(CblasRowMajor, n_samples, n_tasks, -1.0,
                         X_ptr + ii * n_samples, 1, W_ptr + ii * n_tasks, 1,
                         &R[0, 0], n_tasks)

                # update the maximum absolute coefficient update
                d_w_ii = diff_abs_max(n_tasks, W_ptr + ii * n_tasks, wii_ptr)

                if d_w_ii > d_w_max:
                    d_w_max = d_w_ii

                W_ii_abs_max = abs_max(n_tasks, W_ptr + ii * n_tasks)
                if W_ii_abs_max > w_max:
                    w_max = W_ii_abs_max

            if w_max == 0.0 or d_w_max / w_max < d_w_tol or n_iter == max_iter - 1:
                # the biggest coordinate update of this iteration was smaller than
                # the tolerance: check the duality gap as ultimate stopping
                # criterion

                # XtA = np.dot(X.T, R) - l2_reg * W.T
                for ii in range(n_features):
                    for jj in range(n_tasks):
                        XtA[ii, jj] = ddot(
                            n_samples, X_ptr + ii * n_samples, 1,
                            &R[0, 0] + jj, n_tasks
                            ) - l2_reg * W[jj, ii]

                # dual_norm_XtA = np.max(np.sqrt(np.sum(XtA ** 2, axis=1)))
                dual_norm_XtA = 0.0
                for ii in range(n_features):
                    # np.sqrt(np.sum(XtA ** 2, axis=1))
                    XtA_axis1norm = dnrm2(n_tasks, &XtA[0, 0] + ii * n_tasks, 1)
                    if XtA_axis1norm > dual_norm_XtA:
                        dual_norm_XtA = XtA_axis1norm

                # TODO: use squared L2 norm directly
                # R_norm = linalg.norm(R, ord='fro')
                # w_norm = linalg.norm(W, ord='fro')
                R_norm = dnrm2(n_samples * n_tasks, &R[0, 0], 1)
                w_norm = dnrm2(n_features * n_tasks, W_ptr, 1)
                if (dual_norm_XtA > l1_reg):
                    const =  l1_reg / dual_norm_XtA
                    A_norm = R_norm * const
                    gap = 0.5 * (R_norm ** 2 + A_norm ** 2)
                else:
                    const = 1.0
                    gap = R_norm ** 2

                # ry_sum = np.sum(R * y)
                ry_sum = 0.0
                for ii in range(n_samples):
                    for jj in range(n_tasks):
                        ry_sum += R[ii, jj] * Y[ii, jj]

                # l21_norm = np.sqrt(np.sum(W ** 2, axis=0)).sum()
                l21_norm = 0.0
                for ii in range(n_features):
                    # np.sqrt(np.sum(W ** 2, axis=0))
                    l21_norm += dnrm2(n_tasks, W_ptr + n_tasks * ii, 1)

                gap += l1_reg * l21_norm - const * ry_sum + \
                     0.5 * l2_reg * (1 + const ** 2) * (w_norm ** 2)

                if gap < tol:
                    # return if we reached desired tolerance
                    break

    return np.asarray(W), gap, tol, n_iter + 1
