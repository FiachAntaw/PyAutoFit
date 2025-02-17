from functools import reduce
from operator import mul
from typing import (
    Iterable, Tuple, TypeVar, Dict, NamedTuple, Optional, Union
)
import warnings

import numpy as np
from scipy import special
from scipy.special import psi, polygamma
from scipy.linalg import block_diag
from scipy.optimize import OptimizeResult

from autofit.mapper.variable import Variable


class Status(NamedTuple):
    success: bool = True
    messages: Tuple[str, ...] = ()


class FlattenArrays(dict):
    """
    >>> shapes = FlattenArrays(a=(1, 2), b=(2, 3))
    >>> shapes
    FlattenArrays(a=(1, 2), b=(2, 3))
    >>> shapes.flatten(
        a = np.arange(2).reshape(1, 2),
        b = np.arange(6).reshape(2, 3)**2)
    array([ 0,  1,  0,  1,  4,  9, 16, 25])
    >>> shapes.unflatten(
        [ 0,  1,  0,  1,  4,  9, 16, 25])
    {'a': array([[0, 1]]), 'b': array([[ 0,  1,  4],
        [ 9, 16, 25]])}
    """

    def __init__(self, dict_: Dict[Variable, Tuple[int, ...]]):
        super().__init__()

        self.update(dict_)
        self.splits = np.cumsum([
            np.prod(s) for s in self.values()], dtype=int)
        self.inds = [
            slice(i0, i1) for i0, i1 in
            # np.arange(i0, i1, dtype=int) for i0, i1 in
            zip(np.r_[0, self.splits[:-1]], self.splits)]
        self.sizes = {
            k: np.prod(s, dtype=int) for k, s in self.items()}

    @classmethod
    def from_arrays(cls, **arrays: Dict[str, np.ndarray]) -> "FlattenArrays":
        return cls(**{k: np.shape(arr) for k, arr in arrays.items()})

    def flatten(self, arrays_dict: Dict[Variable, np.ndarray]) -> np.ndarray:
        assert all(np.shape(arrays_dict[k]) == shape
                   for k, shape in self.items())
        return np.concatenate([
            np.ravel(arrays_dict[k]) for k in self.keys()])

    def unflatten(self, arr: np.ndarray, ndim=None) -> Dict[str, np.ndarray]:
        arr = np.asanyarray(arr)
        if ndim is None:
            ndim = arr.ndim
        arrays = [
            arr[(ind,) * ndim] for ind in self.inds]
        arr_shapes = [arr.shape[ndim:] for arr in arrays]
        return {
            k: arr.reshape(shape * ndim + arr_shape)
            if shape or arr_shape else arr.item()
            for (k, shape), arr_shape, arr in
            zip(self.items(), arr_shapes, arrays)}

    def flatten2d(self, values: Dict[Variable, np.ndarray]) -> np.ndarray:
        assert all(np.shape(values[k]) == shape * 2
                   for k, shape in self.items())
        return block_diag(*(
            np.reshape(values[k], (n, n))
            for k, n in self.sizes.items()
        ))

    unflatten2d = unflatten

    def __repr__(self):
        shapes = ", ".join(map("{0[0]}={0[1]}".format, self.items()))
        return f"{type(self).__name__}({shapes})"

    @property
    def size(self):
        return self.splits[-1]


class OptResult(NamedTuple):
    mode: Dict[Variable, np.ndarray]
    hess_inv: Dict[Variable, np.ndarray]
    log_norm: float
    full_hess_inv: np.ndarray
    result: OptimizeResult
    status: Status = Status()


def add_arrays(*arrays: np.ndarray) -> np.ndarray:
    """Sums over broadcasting multidimensional arrays
    whilst preserving the total sum

    a = np.arange(10).reshape(1, 2, 1, 5)
    b = np.arange(8).reshape(2, 2, 2, 1)

    >>> add_arrays(a, b).sum()
    73.0
    >>> add_arrays(a, b).shape
    (2, 2, 2, 5)
    >>> a.sum() + b.sum()
    73
    """
    b = np.broadcast(*arrays)
    return sum(a * np.size(a) / b.size for a in arrays)


Axis = Optional[Union[bool, int, Tuple[int, ...]]]


def aggregate(array: np.ndarray, axis: Axis = False, **kwargs) -> np.ndarray:
    """
    aggregates the values of array
    
    if axis is False then aggregate returns the unmodified array

    otherwise aggrate returns np.sum(array, axis=axis, **kwargs)
    """
    if axis is False:
        return array
    else:
        return np.sum(array, axis=axis, **kwargs)


def diag(array: np.ndarray, *ds: Tuple[int, ...]) -> np.ndarray:
    array = np.asanyarray(array)
    d1 = array.shape
    if ds:
        ds = (d1,) + ds
    else:
        ds = (d1, d1)

    out = np.zeros(sum(ds, ()))
    diag_inds = tuple(map(np.ravel, (i for d in ds for i in np.indices(d))))
    out[diag_inds] = array.ravel()
    return out


_M = TypeVar('_M')


def prod(iterable: Iterable[_M], *arg: Tuple[_M]) -> _M:
    """calculates the product of the passed iterable,
    much like sum, if a second argument is passed,
    this is the initial value of the calculation

    Examples
    --------
    >>> prod(range(1, 3))
    2

    >>> prod(range(1, 3), 2.)
    4.
    """
    return reduce(mul, iterable, *arg)


def r2_score(y_true, y_pred, axis=None):
    y_true = np.asanyarray(y_true)
    y_pred = np.asanyarray(y_pred)

    mse = np.square(y_true - y_pred).mean(axis=axis)
    var = y_true.var(axis=axis)

    return 1 - mse / var


class CachedProperty(object):
    """
    A property that is only computed once per instance and then replaces
    itself with an ordinary attribute. Deleting the attribute resets the
    property. 
    
    Source: https://github.com/bottlepy/bottle/commit/fa7733e075da0d790d809aa3d2f53071897e6f76
    """

    def __init__(self, func):
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


cached_property = CachedProperty


def propagate_uncertainty(
        cov: np.ndarray, jac: np.ndarray) -> np.ndarray:
    """Propagates the uncertainty of a covariance matrix given the
    passed Jacobian

    If the variable arrays are multidimensional then will output in
    the shape of the arrays

    see https://en.wikipedia.org/wiki/Propagation_of_uncertainty
    """
    cov = np.asanyarray(cov)

    var_ndim = cov.ndim // 2
    det_ndim = jac.ndim - var_ndim
    det_shape, var_shape = jac.shape[:det_ndim], jac.shape[det_ndim:]
    assert var_shape == cov.shape[:var_ndim] == cov.shape[var_ndim:]

    var_size = np.prod(var_shape, dtype=int)
    det_size = np.prod(det_shape, dtype=int)

    cov2d = cov.reshape((var_size, var_size))
    jac2d = jac.reshape((det_size, var_size))

    det_cov2d = np.linalg.multi_dot((
        jac2d, cov2d, jac2d.T))
    det_cov = det_cov2d.reshape(det_shape + det_shape)
    return det_cov


def numerical_jacobian(x: np.ndarray, func, eps=1e-8, args=(), **kwargs):
    """
    Calculates numerical jacobian of passed function
    """
    x0 = np.array(x)
    f0 = func(x, *args, **kwargs)
    jac = np.empty((np.size(f0), np.size(x0)))
    with np.nditer(x0, op_flags=['readwrite']) as it:
        for i, val in enumerate(it):
            val += eps
            f1 = func(x0, *args, **kwargs)
            jac[:, i] = (f1 - f0) / eps
            val -= eps

    return jac.reshape(np.shape(f0) + np.shape(x0))


def psilog(x: np.ndarray) -> np.ndarray:
    """
    psi(x) - log(x)
    needed when calculating E[ln[x]] when x is a Gamma variable
    """
    return special.digamma(x) - np.log(x)


def grad_psilog(x: np.ndarray) -> np.ndarray:
    """d_x (psi(x) - log(x)) = psi^1(x) - 1/x

    needed when calculating the inverse of psilog(x)
    by using Newton-Raphson

    see:
    invpsilog(c)
    """
    return special.polygamma(1, x) - 1 / x


def invpsilog(c: np.ndarray) -> np.ndarray:
    """
    Solves the equation

    psi(x) - log(x) = c

    where psi is the digamma function. c must be negative.
    The function calculates an approximate inverse which it uses as
    a starting point to 4 iterations of the Newton-Raphson algorithm.
    """
    c = np.asanyarray(c)

    if not np.all(c < 0):
        raise ValueError("values passed must be negative")

    # approximate starting guess
    # -1/x < psilog(x) < -1/(2x)
    A, beta, gamma = 0.38648347, 0.89486989, 0.78578843
    x0 = -(1 - 0.5 * (1 + A * (-c) ** beta) ** -gamma) / c

    # do 4 iterations of Newton Raphson to refine estimate
    for _ in range(4):
        f0 = psilog(x0) - c
        x0 = x0 - f0 / grad_psilog(x0)

    return x0


def grad_betaln(ab):
    psiab = psi(ab.sum(axis=1, keepdims=True))
    return psi(ab) - psiab


def jac_grad_betaln(ab):
    psi1ab = polygamma(1, ab.sum(axis=1, keepdims=True))
    fii = polygamma(1, ab) - psi1ab
    fij = -psi1ab[:, 0]
    return np.array([[fii[:, 0], fij], [fij, fii[:, 1]]]).T


def inv_beta_suffstats(lnX, ln1X):
    """Solve for a, b for, 
    
    psi(a) + psi(a + b) = lnX
    psi(b) + psi(a + b) = ln1X
    """
    _lnX, _ln1X = np.ravel(lnX), np.ravel(ln1X)
    lnXs = np.c_[_lnX, _ln1X]
    
    # Find initial starting location
    Gs = np.exp(lnXs)
    dG = 1 - Gs.sum(axis=1, keepdims=True)
    ab = np.maximum(1, (1 + Gs / dG)/2)
    
    # 5 Newton Raphson itertions is generally enough
    for i in range(5):
        f = grad_betaln(ab) - lnXs
        jac = jac_grad_betaln(ab)
        ab += np.linalg.solve(jac, - f)
        
    if np.any(ab < 0):
        warnings.warn(
            "invalid negative parameters found for inv_beta_suffstats, "
            "clampling value to 0.5",
            RuntimeWarning
        )
        b = np.clip(ab, 0.5, None)

    shape = np.shape(lnX)
    if shape:
        a = ab[:, 0].reshape(shape)
        b = ab[:, 1].reshape(shape)
    else:
        a, b = ab[0,:]
        
    return a, b


def numerical_jacobian(x, func, eps=1e-8, args=(), **kwargs):
    x = np.array(x)
    f0 = func(x, *args, **kwargs)
    jac = np.empty(np.shape(f0) + np.shape(x))
    fslice = (slice(None), ) * np.ndim(f0)
    with np.nditer(x, flags=['multi_index'], op_flags=['readwrite']) as it:
        for xi in it:
            xi += eps
            f1 = func(x, *args, **kwargs)
            jac[fslice + it.multi_index] = (f1 - f0)/eps
            xi -= eps
            
    return jac


def rescale_to_artists(artists, ax=None):
    import matplotlib.pyplot as plt
    ax = ax or plt.gca()
    while True:
        r = ax.figure.canvas.get_renderer()
        extents = [
            t.get_window_extent(
                renderer=r
            ).transformed(
                ax.transData.inverted()
            )
            for t in artists
        ]
        min_extent = np.min(
            [e.min for e in extents], axis=0
        )
        max_extent = np.max(
            [e.max for e in extents], axis=0
        )
        min_lim, max_lim = zip(ax.get_xlim(), ax.get_ylim())

        # Sometimes the window doesn't always rescale first time around
        if (min_extent < min_lim).any() or (max_extent > max_lim).any():
            extent = max_extent - min_extent
            max_extent += extent * 0.05
            min_extent -= extent * 0.05
            xlim, ylim = zip(
                np.minimum(min_lim, min_extent), np.maximum(max_lim, max_extent)
            )
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
        else:
            break

    return xlim, ylim
