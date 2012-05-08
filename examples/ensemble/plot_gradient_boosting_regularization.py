"""
================================
Gradient Boosting regularization
================================

Illustration of the effect of different regularization strategies
for Gradient Boosting. The example is taken from Hastie et al 2009.

The loss function used is binomial deviance. In combination with
shrinkage, stochastic gradient boosting (Sample 0.5) can produce
more accurate models.
Subsampling without shrinkage usually does poorly.

.. [1] T. Hastie, R. Tibshirani and J. Friedman, "Elements of Statistical
    Learning Ed. 2", Springer, 2009.
"""
print __doc__

# Author: Peter Prettenhofer <peter.prettenhofer@gmail.com>
#
# License: BSD

import numpy as np
import pylab as pl
from sklearn import ensemble
from sklearn import datasets


X, y = datasets.make_hastie_10_2(n_samples=12000, random_state=1)
X = X.astype(np.float32)

X_train, X_test = X[:2000], X[2000:]
y_train, y_test = y[:2000], y[2000:]

original_params = {'n_estimators': 1000, 'max_depth': 2, 'random_state': 1,
                   'min_samples_split': 5}

pl.figure()

for label, color, setting in [('No shrinkage', 'orange',
                               {'learn_rate': 1.0, 'subsample': 1.0}),
                              ('Shrink=0.1', 'turquoise',
                               {'learn_rate': 0.1, 'subsample': 1.0}),
                              ('Sample=0.5', 'blue',
                               {'learn_rate': 1.0, 'subsample': 0.5}),
                              ('Shrink=0.1, Sample=0.5', 'gray',
                               {'learn_rate': 0.1, 'subsample': 0.5})]:
    params = dict(original_params)
    params.update(setting)

    clf = ensemble.GradientBoostingClassifier(**params)
    clf.fit(X_train, y_train)

    # compute test set deviance
    test_deviance = np.zeros((params['n_estimators'],), dtype=np.float64)

    for i, y_pred in enumerate(clf.staged_decision_function(X_test)):
        test_deviance[i] = clf.loss_(y_test, y_pred)

    pl.plot(np.arange(test_deviance.shape[0]) + 1, test_deviance, '-',
            color=color, label=label)

pl.title('Deviance')
pl.legend(loc='upper left')
pl.xlabel('Boosting Iterations')
pl.ylabel('Test Set Deviance')

pl.show()
