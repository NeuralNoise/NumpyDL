"""
Functions to generate Theano update dictionaries for training.

The update functions implement different methods to control the learning
rate for use with stochastic gradient descent.

Update functions take a loss expression or a list of gradient expressions and
a list of parameters as input and return an ordered dictionary of updates:


Examples
--------
Using :class:`SGD` to define an update dictionary for a toy
example network:

>>> import npdl
>>> from npdl.activations import ReLU
>>> from npdl.activations import Softmax
>>> from npdl.objectives import SCCE
>>> model = npdl.model.Model()
>>> model.add(npdl.layers.Dense(n_out=100, n_in=50, activation=ReLU()))
>>> model.add(npdl.layers.Dense(n_out=200, activation=ReLU()))
>>> model.add(npdl.layers.Dense(n_out=100, activation=ReLU()))
>>> model.add(npdl.layers.Dense(n_out=10, activation=Softmax()))
>>> model.compile(loss=SCCE(), optimizer=npdl.optimizers.SGD(lr=0.005))

"""

import copy
import numpy as np

from .initializations import _zero


class Optimizer(object):
    """Abstract optimizer base class.

    Note: this is the parent class of all optimizers, not an actual optimizer
    that can be used for training models.

    Parameters
    ----------
    clip : float
        If smaller than 0, do not apply parameter clip.
    lr : float
        The learning rate controlling the size of update steps
    """

    def __init__(self, lr=0.001, clip=-1):
        self.lr = lr
        self.clip = clip

    def update(self, params, grads):
        """Update parameters.

        Parameters
        ----------
        params : list
            A list of parameters in model.
        grads : list
            A list of gradients in model.
        """
        raise NotImplementedError

    def __str__(self):
        return self.__class__.__name__


class SGD(Optimizer):
    """Stochastic Gradient Descent (SGD) updates

    Generates update expressions of the form:

    * ``param := param - learning_rate * gradient``
    """
    def __init__(self, *args, **kwargs):
        super(SGD, self).__init__(*args, **kwargs)

    def update(self, params, grads):
        for p, g in zip(params, grads):
            p -= self.lr * npdl_clip(g, self.clip)


class Momentum(Optimizer):
    """Stochastic Gradient Descent (SGD) updates with momentum

    Generates update expressions of the form:

    * ``velocity := momentum * velocity - learning_rate * gradient``
    * ``param := param + velocity``

    Parameters
    ----------
    momentum : float
        The amount of momentum to apply. Higher momentum results in
        smoothing over more update steps. Defaults to 0.9.

    Notes
    -----
    Higher momentum also results in larger update steps. To counter that,
    you can optionally scale your learning rate by `1 - momentum`.

    """

    def __init__(self, momentum=0.9, *args, **kwargs):
        super(Momentum, self).__init__(*args, **kwargs)

        self.momentum = momentum

        self.velocity = None

    def update(self, params, grads):
        # init the velocities
        if self.velocity is None:
            self.velocity = [_zero(p.shape) for p in params]

        # update the parameters
        for v, p, g in zip(self.velocity, params, grads):
            v = self.momentum * v - self.lr * g
            p += v


class NesterovMomentum(Momentum):
    """Stochastic Gradient Descent (SGD) updates with Nesterov momentum

    Generates update expressions of the form:

    * ``velocity := momentum * velocity - learning_rate * gradient``
    * ``param := param + momentum * velocity - learning_rate * gradient``

    Notes
    -----
    Higher momentum also results in larger update steps. To counter that,
    you can optionally scale your learning rate by `1 - momentum`.

    The classic formulation of Nesterov momentum (or Nesterov accelerated
    gradient) requires the gradient to be evaluated at the predicted next
    position in parameter space. Here, we use the formulation described at
    https://github.com/lisa-lab/pylearn2/pull/136#issuecomment-10381617,
    which allows the gradient to be evaluated at the current parameters.

    """
    def __init__(self, *args, **kwargs):
        super(NesterovMomentum, self).__init__(*args, **kwargs)

    def update(self, params, grads):
        # init the velocities
        if self.velocity is None:
            self.velocity = [_zero(p.shape) for p in params]

        # update the parameters
        for v, p, g in zip(self.velocity, params, grads):
            v = self.momentum * v - self.lr * g
            p += (self.momentum * v - self.lr * g)


class Adagrad(Optimizer):
    """Adagrad updates

    Scale learning rates by dividing with the square root of accumulated
    squared gradients. See [1]_ for further description.

    Parameters
    ----------
    epsilon : float
        Small value added for numerical stability.

    Notes
    -----
    Using step size eta Adagrad calculates the learning rate for feature i at
    time step t as:

    .. math:: \\eta_{t,i} = \\frac{\\eta}
       {\\sqrt{\\sum^t_{t^\\prime} g^2_{t^\\prime,i}+\\epsilon}} g_{t,i}

    as such the learning rate is monotonically decreasing.

    Epsilon is not included in the typical formula, see [2]_.

    References
    ----------
    .. [1] Duchi, J., Hazan, E., & Singer, Y. (2011):
           Adaptive subgradient methods for online learning and stochastic
           optimization. JMLR, 12:2121-2159.

    .. [2] Chris Dyer:
           Notes on AdaGrad. http://www.ark.cs.cmu.edu/cdyer/adagrad.pdf
    """

    def __init__(self, epsilon=1e-6, *args, **kwargs):
        super(Adagrad, self).__init__(*args, **kwargs)

        self.epsilon = epsilon

        self.cache = None

    def update(self, params, grads):
        # init cache
        if self.cache is None:
            self.cache = [_zero(g.shape) for g in grads]

        # update parameters
        for c, p, g in zip(self.cache, params, grads):
            c += np.power(g, 2)
            p -= self.lr * g / (np.sqrt(c) + self.epsilon)


class RMSprop(Optimizer):
    """RMSProp updates

    Scale learning rates by dividing with the moving average of the root mean
    squared (RMS) gradients. See [1]_ for further description.

    Parameters
    ----------
    lr : float
        The learning rate controlling the size of update steps

    Notes
    -----
    `rho` should be between 0 and 1. A value of `rho` close to 1 will decay the
    moving average slowly and a value close to 0 will decay the moving average
    fast.

    Using the step size :math:`\\eta` and a decay factor :math:`\\rho` the
    learning rate :math:`\\eta_t` is calculated as:

    .. math::
       r_t &= \\rho r_{t-1} + (1-\\rho)*g^2\\\\
       \\eta_t &= \\frac{\\eta}{\\sqrt{r_t + \\epsilon}}

    References
    ----------
    .. [1] Tieleman, T. and Hinton, G. (2012):
           Neural Networks for Machine Learning, Lecture 6.5 - rmsprop.
           Coursera. http://www.youtube.com/watch?v=O3sxAc4hxZU (formula @5:20)
    """

    def __init__(self, *args, **kwargs):
        super(RMSprop, self).__init__(*args, **kwargs)


class Adadelta(Optimizer):
    """ Adadelta updates

    Scale learning rates by the ratio of accumulated gradients to accumulated
    updates, see [1]_ and notes for further description.

    Parameters
    ----------
    lr : float
        The learning rate controlling the size of update steps

    Notes
    -----
    rho should be between 0 and 1. A value of rho close to 1 will decay the
    moving average slowly and a value close to 0 will decay the moving average
    fast.

    rho = 0.95 and epsilon=1e-6 are suggested in the paper and reported to
    work for multiple datasets (MNIST, speech).

    In the paper, no learning rate is considered (so learning_rate=1.0).
    Probably best to keep it at this value.
    epsilon is important for the very first update (so the numerator does
    not become 0).

    Using the step size eta and a decay factor rho the learning rate is
    calculated as:

    .. math::
       r_t &= \\rho r_{t-1} + (1-\\rho)*g^2\\\\
       \\eta_t &= \\eta \\frac{\\sqrt{s_{t-1} + \\epsilon}}
                             {\sqrt{r_t + \epsilon}}\\\\
       s_t &= \\rho s_{t-1} + (1-\\rho)*(\\eta_t*g)^2

    References
    ----------
    .. [1] Zeiler, M. D. (2012):
           ADADELTA: An Adaptive Learning Rate Method.
           arXiv Preprint arXiv:1212.5701.
    """

    def __init__(self, *args, **kwargs):
        super(Adadelta, self).__init__(*args, **kwargs)


class Adam(Optimizer):
    """Adam updates

    Adam updates implemented as in [1]_.

    Parameters
    ----------
    lr : float
        The learning rate controlling the size of update steps

    Notes
    -----
    The paper [1]_ includes an additional hyperparameter lambda. This is only
    needed to prove convergence of the algorithm and has no practical use
    (personal communication with the authors), it is therefore omitted here.

    References
    ----------
    .. [1] Kingma, Diederik, and Jimmy Ba (2014):
           Adam: A Method for Stochastic Optimization.
           arXiv preprint arXiv:1412.6980.
    """

    def __init__(self, *args, **kwargs):
        super(Adam, self).__init__(*args, **kwargs)


class Adamax(Optimizer):
    """Adamax updates

    Adamax updates implemented as in [1]_. This is a variant of of the Adam
    algorithm based on the infinity norm.

    Parameters
    ----------
    lr : float
        The learning rate controlling the size of update steps

    References
    ----------
    .. [1] Kingma, Diederik, and Jimmy Ba (2014):
           Adam: A Method for Stochastic Optimization.
           arXiv preprint arXiv:1412.6980.
    """

    def __init__(self, *args, **kwargs):
        super(Adamax, self).__init__(*args, **kwargs)


def npdl_clip(grad, boundary):
    if boundary > 0:
        return np.clip(grad, -boundary, boundary)
    else:
        return grad


def get(optimizer):
    if optimizer.__class__.__name__ == 'str':
        if optimizer in ['sgd', 'SGD']:
            return SGD()
        if optimizer in ['momentum', 'Momentum']:
            return Momentum()
        if optimizer in ['nesterov_momentum', 'NesterovMomentum']:
            return NesterovMomentum()
        if optimizer in ['adagrad', 'Adagrad']:
            return Adagrad()
        if optimizer in ['rmsprop', 'RMSprop']:
            return RMSprop()
        if optimizer in ['adadelta', 'Adadelta']:
            return Adadelta()
        if optimizer in ['adam', 'Adam']:
            return Adam()
        if optimizer in ['adamax', 'Adamax']:
            return Adamax()
        raise ValueError('Unknown optimizer name: {}.'.format(optimizer))

    elif isinstance(optimizer, Optimizer):
        return copy.deepcopy(optimizer)

    else:
        raise ValueError("Unknown type: {}.".format(optimizer.__class__.__name__))

