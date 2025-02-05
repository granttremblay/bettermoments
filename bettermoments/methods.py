"""
All the methods used for collapsing the cube.
"""

import numpy as np
import multiprocessing
from itertools import repeat


# -- COLLAPSE METHODS -- *


def collapse_zeroth(velax, data, rms):
    r"""
    Collapses the cube by integrating along the spectral axis. It will return
    the integrated intensity along the spectral axis, ``M0``, and the
    associated uncertainty, ``dM0``. Following `Teague (2019)`_ these are
    calculated by,

    .. math::
        M_0 = \sum_{i}^N I_i \, \Delta v_{{\rm chan},\,i}

    and

    .. math::
        M_0 = \sqrt{\sum_{i\,(I_i > 0)}^N \sigma_i^2 \cdot \Delta v_{{\rm chan},\,i}^2}

    where :math:`\Delta v_i` and :math:`I_i` are the chanenl width and flux
    density at the :math:`i^{\rm th}` channel, respectively and the sum goes
    over the whole ``axis``.

    .. _Teague (2019): https://iopscience.iop.org/article/10.3847/2515-5172/ab2125

    Args:
        velax (ndarray): Velocity axis of the cube.
        data (ndarray): Flux densities or brightness temperature array. Assumes
            that the first axis is the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.

    Returns:
        ``M0`` (`ndarray`), ``dM0`` (`ndarray`):
            ``M0``, the integrated intensity along provided axis and ``dM0``,
            the uncertainty on ``M0`` in the same units as ``M0``.
    """
    chan = np.diff(velax).mean()
    npix = np.sum(data != 0.0, axis=0)
    M0 = np.trapz(data, dx=chan, axis=0)
    dM0 = chan * rms * npix**0.5 * np.ones(M0.shape)
    if M0.shape != data[0].shape:
        raise ValueError("`data` not collapsed correctly." +
                         " Expected shape: {},".format(data[0].shape) +
                         " returned shape: {}.".format(M0.shape))
    if M0.shape != dM0.shape:
        raise ValueError("Mismatch in `M0` and `dM0` shapes: "
                         "{} and {}.".format(M0.shape, dM0.shape))
    return M0, dM0


def collapse_first(velax, data, rms):
    r"""
    Collapses the cube using the intensity weighted average velocity (or first
    moment map). For a symmetric line profile this will be the line center,
    however for highly non-symmetric line profiles, this will not give a
    meaningful result. Following `Teague (2019)`_, the line center is given by,

    .. math::
        M_1 = \frac{\sum_i^N I_i v_i}{\sum_i^N I_i}

    where :math:`v_i` and :math:`I_i` are the velocity and flux density at the
    :math:`i^{\rm th}` channel, respectively and the sum goes over the whole
    ``axis``. In addition, the uncertainty is given by,

    .. math::
        \delta M_1 = \sqrt{\sum_{i\,(I_i > 0)}^N \sigma_i^2 \cdot (v_i - M_1)^2}

    where :math:`\sigma_i` is the rms noise.

    .. _Teague (2019): https://iopscience.iop.org/article/10.3847/2515-5172/ab2125

    Args:
        velax (ndarray): Velocity axis of the cube.
        data (ndarray): Flux densities or brightness temperature array. Assumes
            that the zeroth axis is the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.

    Returns:
        ``M1`` (`ndarray`), ``dM1`` (`ndarray`):
            ``M1``, the intensity weighted average velocity in units of
            ``velax`` and ``dM1``, the uncertainty in the intensity weighted
            average velocity with same units as ``v0``.
    """
    chan = np.diff(velax).mean()
    vpix = chan * np.arange(data.shape[0]) + velax[0]
    vpix = vpix[:, None, None] * np.ones(data.shape)

    weights = 1e-10 * np.random.rand(data.size).reshape(data.shape)
    weights = np.where(data != 0.0, abs(data), weights)
    M1 = np.average(vpix, weights=weights, axis=0)
    dM1 = (vpix - M1[None, :, :]) * rms / np.sum(weights, axis=0)
    dM1 = np.sqrt(np.sum(dM1**2, axis=0))

    npix = np.sum(data != 0.0, axis=0)
    M1 = np.where(npix >= 1.0, M1, np.nan)
    dM1 = np.where(npix >= 1.0, dM1, np.nan)

    if M1.shape != data[0].shape:
        raise ValueError("`data` not collapsed correctly." +
                         " Expected shape: {},".format(data[0].shape) +
                         " returned shape: {}.".format(M1.shape))
    if M1.shape != dM1.shape:
        raise ValueError("Mismatch in `M1` and `dM1` shapes: "
                         "{} and {}.".format(M1.shape, dM1.shape))
    return M1, dM1


def collapse_second(velax, data, rms):
    r"""
    Collapses the cube using the intensity-weighted average velocity dispersion
    (or second moment). For a symmetric line profile this will be a measure of
    the line width. Following `Teague (2019)`_ this is calculated by,

    .. math::
        M_2 = \sqrt{\frac{\sum_i^N I_i (v_i - M_1)^2}{{\sum_i^N I_i}}}

    where :math:`M_1` is the first moment and :math:`v_i` and :math:`I_i` are
    the velocity and flux density at the :math:`i^{\rm th}` channel,
    respectively. The uncertainty is given by,

    .. math::
        \delta M_2 &= \frac{1}{2 M_2} \cdot \sqrt{\sum_{i\,(I_i > 0)}^N \sigma_i^2 \cdot \big[(v_i - M_1)^2 - M_2^2\big]^2}

    where :math:`\sigma_i` is the rms noise in the :math:`i^{\rm th}` channel.

    .. _Teague (2019): https://iopscience.iop.org/article/10.3847/2515-5172/ab2125

    Args:
        velax (ndarray): Velocity axis of the cube.
        data (ndarray): Flux densities or brightness temperature array. Assumes
            that the first axis is the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.

    Returns:
        ``M2`` (ndarray), ``dM2`` (ndarray):
            ``M2`` is the intensity weighted velocity dispersion with units of
            ``velax``.  ``dM2`` is the unceratinty of ``M2`` in the same units.
    """
    chan = np.diff(velax).mean()
    vpix = chan * np.arange(data.shape[0]) + velax[0]
    vpix = vpix[:, None, None] * np.ones(data.shape)

    weights = 1e-10 * np.random.rand(data.size).reshape(data.shape)
    weights = np.where(data != 0.0, abs(data), weights)

    M1 = collapse_first(velax=velax, data=data, rms=rms)[0]
    M1 = M1[None, :, :] * np.ones(data.shape)
    M2 = np.sum(weights * (vpix - M1)**2, axis=0) / np.sum(weights, axis=0)
    M2 = np.sqrt(M2)

    dM2 = ((vpix - M1)**2 - M2**2) * rms / np.sum(weights, axis=0)
    dM2 = np.sqrt(np.sum(dM2**2, axis=0)) / 2. / M2

    npix = np.sum(data != 0.0, axis=0)
    M2 = np.where(npix >= 1.0, M2, np.nan)
    dM2 = np.where(npix >= 1.0, dM2, np.nan)

    if M2.shape != data[0].shape:
        raise ValueError("`data` not collapsed correctly." +
                         " Expected shape: {},".format(data[0].shape) +
                         " returned shape: {}.".format(M2.shape))
    if M2.shape != dM2.shape:
        raise ValueError("Mismatch in `M2` and `dM2` shapes: "
                         "{} and {}.".format(M2.shape, dM2.shape))
    return M2, dM2


def collapse_eighth(velax, data, rms):
    """
    Take the peak value along the provided axis. The uncertainty is the RMS
    noise of the image.

    Args:
        velax (ndarray): Velocity axis of the cube. Not needed.
        data (ndarray): Flux densities or brightness temperature array. Assumes
            that the first axis is the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.

    Returns:
        ``M8`` (`ndarray`), ``dM8`` (`ndarray`):
            The peak value, ``M8``, and the associated uncertainty, ``dM8``.
    """
    M8 = np.max(data, axis=0)
    dM8 = rms * np.ones(M8.shape)
    return M8, dM8


def collapse_ninth(velax, data, rms):
    """
    Take the velocity of the peak intensity along the provided axis. The
    uncertainty is half the channel width.

    Args:
        velax (ndarray): Velocity axis of the cube.
        data (ndarray): Flux densities or brightness temperature array. Assumes
            that the first axis is the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.

    Returns:
        ``M9`` (`ndarray`), ``dM9`` (`ndarray`):
            The velocity value of the peak value, ``M9``, and the associated
            uncertainty, ``dM9``.
    """
    M9 = velax[np.argmax(data, axis=0)]
    dM9 = 0.5 * abs(np.diff(velax).mean()) * np.ones(M9.shape)
    return M9, dM9


def collapse_gaussian(velax, data, rms, indices=None, chunks=1, **kwargs):
    r"""
    Collapse the cube by fitting a Gaussian line profile to each pixel. This
    function is a wrapper of `collapse_analytical` which provides more
    details about the arguments.

    Args:
        velax (ndarray): Velocity axis of the cube.
        data (ndarray): Maksed intensity or brightness temperature array. The
            first axis must be the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.
        indices (Optional[list]): A list of pixels described by
            ``(y_idx, x_idx)`` tuples to fit. If none are provided, will fit
            all pixels.
        chunks (Optional[int]): Split the cube into ``chunks`` sections and
            run the fits with separate processes through
            ``multiprocessing.pool``.

    Returns ``gv0, dgv0, gdV, dgdV, gFnu, dgFnu``:
        TBD
    """
    return collapse_analytical(velax=velax, data=data, rms=rms,
                               model_function='gaussian', indices=indices,
                               chunks=chunks, **kwargs)


def collapse_gaussthick(velax, data, rms, indices=None, chunks=1, **kwargs):
    r"""
    Collapse the cube by fitting a Gaussian line profile with an optically
    thick core to each pixel. This function is a wrapper of
    `collapse_analytical` which provides more details about the arguments.

    Args:
        velax (ndarray): Velocity axis of the cube.
        data (ndarray): Maksed intensity or brightness temperature array. The
            first axis must be the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.
        indices (Optional[list]): A list of pixels described by
            ``(y_idx, x_idx)`` tuples to fit. If none are provided, will fit
            all pixels.
        chunks (Optional[int]): Split the cube into ``chunks`` sections and
            run the fits with separate processes through
            ``multiprocessing.pool``.

    Returns ``gv0, dgv0, gdV, dgdV, gFnu, dgFnu, gtau, dgtau``:
        TBD
    """
    return collapse_analytical(velax=velax, data=data, rms=rms,
                               model_function='gaussthick', indices=indices,
                               chunks=chunks, **kwargs)


def collapse_gausshermite(velax, data, rms, indices=None, chunks=1, **kwargs):
    r"""
    Collapse the cube by fitting a Gaussian line profile with an optically
    thick core to each pixel. This function is a wrapper of
    `collapse_analytical` which provides more details about the arguments.

    Args:
        velax (ndarray): Velocity axis of the cube.
        data (ndarray): Maksed intensity or brightness temperature array. The
            first axis must be the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.
        indices (Optional[list]): A list of pixels described by
            ``(y_idx, x_idx)`` tuples to fit. If none are provided, will fit
            all pixels.
        chunks (Optional[int]): Split the cube into ``chunks`` sections and
            run the fits with separate processes through
            ``multiprocessing.pool``.

    Returns ``ghv0, dghv0, ghdV, dghdV, ghFnu, dghFnu, ghh3, dghh3, ghh4, dghh4``:
        TBD
    """
    return collapse_analytical(velax=velax, data=data, rms=rms,
                               model_function='gausshermite', indices=indices,
                               chunks=chunks, **kwargs)


def collapse_analytical(velax, data, rms, model_function, indices=None,
                        chunks=1, **kwargs):
    r"""
    Collapse the cube by fitting an analytical form to each pixel, including
    the option to use an MCMC sampler which has been found to be more forgiving
    when it comes to noisy data. The user can also specify ``chunks`` which
    will split the data into that many chunks and pass each chunk to a separate
    process using ``multiprocessing.pool``.

    For more information on ``kwargs``, see the ``fit_cube`` documentation.

    Args:
        velax (ndarray): Velocity axis of the cube.
        data (ndarray): Maksed intensity or brightness temperature array. The
            first axis must be the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.
        model_function (str): Name of the model function to fit to the data.
            Must be a function withing ``profiles.py``.
        indices (Optional[list]): A list of pixels described by
            ``(y_idx, x_idx)`` tuples to fit. If none are provided, will fit
            all pixels.
        chunks (Optional[int]): Split the cube into ``chunks`` sections and
            run the fits with separate processes through
            ``multiprocessing.pool``.

    Returns:
        results_array (ndarray): An array containing all the fits. The first
            axis contains the mean and standard deviation of each posterior
            distribution.
    """
    from .mcmc_sampling import fit_cube
    from .profiles import free_params

    # Unless provided, fit all spaxels where there are some finite values.
    # By default, we require each spectrum to have twice as many finite values
    # as there are free parameters in the model being fit.

    if indices is None:
        indices = _get_finite_pixels(data, 2.0 * free_params(model_function))

    # Split these pixels evenly into chunks to pass off to processes.

    chunk_edges = np.linspace(0, indices.shape[0], chunks+1)
    chunk_indices = np.digitize(np.arange(indices.shape[0]), chunk_edges)
    chunk_indices = [indices[chunk_indices == i] for i in range(1, chunks+1)]
    chunk_indices = np.array(chunk_indices)
    assert chunk_indices.shape[0] == chunks

    # Pass these off to different pools.

    args = [(velax, data, rms, model_function, idx) for idx in chunk_indices]
    with multiprocessing.Pool(processes=chunks) as pool:
        results = _starmap_with_kwargs(pool, fit_cube, args, repeat(kwargs))
    results = np.concatenate(results, axis=0)
    assert results.shape[0] == indices.shape[0]
    results = results.reshape(results.shape[0], -1)

    # Populate arrays with results and return.

    results_arrays = np.ones((*data.shape[1:], results.shape[1])) * np.nan
    for idx, result in zip(indices, results):
        results_arrays[idx[0], idx[1]] = result
    results_arrays = np.rollaxis(results_arrays, -1, 0)
    return results_arrays


def collapse_quadratic(velax, data, rms):
    """
    Collapse the cube using the quadratic method presented in `Teague &
    Foreman-Mackey (2018)`_. Will return the line center, ``v0``, and the
    uncertainty on this, ``dv0``, as well as the line peak, ``Fnu``, and the
    uncertainty on that, ``dFnu``. This provides the sub-channel precision of
    :func:`bettermoments.collapse_cube.collapse_first` with the robustness to
    noise from :func:`bettermoments.collapse_cube.collapse_ninth`.

    .. _Teague & Foreman-Mackey (2018): https://iopscience.iop.org/article/10.3847/2515-5172/aae265

    Args:
        velax (ndarray): Velocity axis of the cube.
        data (ndarray): Flux density or brightness temperature array. Assumes
            that the zeroth axis is the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.

    Returns:
        ``v0`` (`ndarray`), ``dv0`` (`ndarray`), ``Fnu`` (`ndarray`), ``dFnu`` (`ndarray`):
            ``v0``, the line center in the same units as ``velax`` with ``dv0``
            as the uncertainty on ``v0`` in the same units as ``velax``.
            ``Fnu`` is the line peak in the same units as the
            ``data`` with associated uncertainties, ``dFnu``.
    """
    from bettermoments.quadratic import quadratic
    chan = np.diff(velax).mean()
    return np.squeeze(quadratic(data, x0=velax[0], dx=chan, uncertainty=rms))


def collapse_maximum(velax, data, rms):
    """
    A wrapper returning the result of both
    :func:`bettermoments.collapse_cube.collapse_eighth` and
    :func:`bettermoments.collapse_cube.collapse_ninth`.

    Args:
        velax (ndarray): Velocity axis of the cube.
        data (ndarray): Flux densities or brightness temperature array. Assumes
            that the first axis is the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.

    Returns:
        ``M8`` (`ndarray`), ``dM8`` (`ndarray`), ``M9`` (`ndarray`), ``dM9`` (`ndarray`):
            The peak value, ``M8``, and the associated uncertainty, ``dM8``.
            The velocity value of the peak value, ``M9``, and the associated
            uncertainty, ``dM9``.
    """
    M8, dM8 = collapse_eighth(velax=velax, data=data, rms=rms)
    M9, dM9 = collapse_ninth(velax=velax, data=data, rms=rms)
    return M8, dM8, M9, dM9


def collapse_width(velax, data, rms):
    r"""
    Returns an effective width, a rescaled ratio of the integrated intensity
    and the line peak. For a Gaussian line profile this would be the Doppler
    width as the total intensity is given by,

    .. math::
        M_0 = \sum_{i}^N I_i \, \Delta v_{{\rm chan},\,i}

    where :math:`\Delta v_i` and :math:`I_i` are the chanenl width and flux
    density at the :math:`i^{\rm th}` channel. If the line profile is Gaussian,
    then equally

    .. math::
        M_0 = \sqrt{\pi} \times F_{\nu} \times \Delta V

    where :math:`F_{\nu}` is the peak value of the line and :math:`\Delta V` is
    the Doppler width of the line. As :math:`M_0` and :math:`F_{\nu}` are
    readily calculated using
    :func:`bettermoments.collapse_cube.collapse_zeroth` and
    :func:`bettermoments.collapse_cube.collapse_quadratic`, respectively,
    :math:`\Delta V` can calculated through :math:`\Delta V = M_{0} \, / \,
    (\sqrt{\pi} \, F_{\nu})`. This should be more robust against noise than
    second moment maps.

    Args:
        velax (ndarray): Velocity axis of the cube.
        data (ndarray): Flux densities or brightness temperature array. Assumes
            that the first axis is the velocity axis.
        rms (float): Noise per pixel in same units as ``data``.

    Returns:
        ``dV`` (`ndarray`), ``ddV`` (`ndarray`):
            The effective velocity dispersion, ``dV`` and ``ddV``, the
            associated uncertainty.
    """
    M0, dM0 = collapse_zeroth(velax=velax, data=data, rms=rms)
    _, _, Fnu, dFnu = collapse_quadratic(velax=velax, data=data, rms=rms)
    dV = M0 / Fnu / np.sqrt(np.pi)
    ddV = dV * np.hypot(dFnu / Fnu, dM0 / M0)
    return abs(dV), abs(ddV)


# -- HELPER FUNCTIONS -- #


def available_collapse_methods():
    """Prints the available methods for collapsing the datacube."""
    funcs = ['zeroth', 'first', 'second', 'eighth', 'ninth',
             'maximum', 'quadratic', 'width', 'gaussian',
             'gaussthick', 'gausshermite']
    txt = 'Available methods are:\n'
    txt += '\n'
    txt += '\t {:12} (integrated intensity)\n'
    txt += '\t {:12} (intensity weighted average velocity)\n'
    txt += '\t {:12} (intensity weighted velocity dispersion)\n'
    txt += '\t {:12} (peak intensity)\n'
    txt += '\t {:12} (velocity channel of peak intensity)\n'
    txt += '\t {:12} (both collapse_eighth and collapse_ninth)\n'
    txt += '\t {:12} (quadratic fit to peak intensity)\n'
    txt += '\t {:12} (effective width for a Gaussian profile)\n'
    txt += '\t {:12} (gaussian fit)\n'
    txt += '\t {:12} (gaussian with optically thick core fit)\n'
    txt += '\t {:12} (gaussian-hermite expansion fit)\n'
    txt += '\n'
    txt += 'Call the function with `collapse_{{method_name}}`.'
    print(txt.format(*funcs))


def collapse_method_products(method):
    """Prints the products from each ``collapse_method``."""
    returns = {}
    returns['zeroth'] = 'M0, dM0'
    returns['first'] = 'M1, dM1'
    returns['second'] = 'M2, dM2'
    returns['eighth'] = 'M8, dM8'
    returns['ninth'] = 'M9, dM9'
    returns['maximum'] = 'M8, dM8, M9, dM9'
    returns['quadratic'] = 'v0, dv0, Fnu, dFnu'
    returns['width'] = 'dV, ddV'
    returns['gaussian'] = 'gv0, dgv0, gdV, dgdV, gFnu, dgFnu'
    returns['gaussthick'] = 'gv0, dgv0, gdV, dgdV, gFnu, dgFnu, gtau, dgtau'
    returns['gausshermite'] = 'ghv0, dghv0, ghdV, dghdV, ghFnu, dghFnu '
    returns['gausshermite'] += 'ghh3, dghh3, ghh4, dghh4'
    try:
        return returns[method]
    except KeyError:
        print('`{}` not found.'.format(method))
        available_collapse_methods()


def _starmap_with_kwargs(pool, fn, args_iter, kwargs_iter):
    """Allow us to pass args and kwargs to ``pool.starmap``."""
    args_for_starmap = zip(repeat(fn), args_iter, kwargs_iter)
    return pool.starmap(_apply_args_and_kwargs, args_for_starmap)


def _apply_args_and_kwargs(fn, args, kwargs):
    """Unpack the args and kwargs."""
    return fn(*args, **kwargs)


def _get_finite_pixels(data, min_finite=3):
    """
    Returns the (yidx, xidx) tuple for each of the pixels which have at least
    ``min_finite`` finite samples along the zeroth axis. A good rule of thumb
    is twice the number of free parameters for the model.

    Args:
        data (array): The data that will be used for the fitting.
        min_finite (optional[int]): Minimum number of finite samples along the
            zeroth axis. Must be positive.

    Returns:
        indices: A list of (yidx, xidx) tuples of all finite pixels.
    """
    assert min_finite > 0, "Must have at least one finite sample to fit."""
    finite_spaxels = np.sum(data != 0.0, axis=0) > int(min_finite)
    indices = np.indices(data[0].shape).reshape(2, data[0].size).T
    return indices[finite_spaxels.flatten()]
