import numpy as np
from scipy.stats import skew
import random
from numpy.fft import fft, ifft
from pycdms.detcal.misc.utils import ofamp

def removeoutliers(x, maxiter=20, skewTarget=0.05):
    """
    Function to return indices of inlying points, removing points by minimizing the skewness
    
    Parameters
    ----------
        x : ndarray
            Array of real-valued variables from which to remove outliers.
        maxiter : float, optional
            Maximum number of iterations to continue to minimize skewness. Default is 20.
        skewTarget : float, optional
            Desired residual skewness of distribution. Default is 0.05.
    
    Returns
    -------
        inds : 
            Boolean indices indicating which values to select/reject, same length as x.
    """
    
    i=1
    inds=(x != np.inf)
    sk=skew(x[inds])
    while(sk > skewTarget):
        dmed=x-np.median(x[inds])
        dist=np.min([abs(min(dmed)),abs(max(dmed))])
        inds=inds & (abs(dmed) < dist)
        sk=skew(x[inds])
        if(i > maxiter):
            break
        i+=1

    return inds

def iterstat(data,cut=3,precision=1000.0):
    """
    Function to iteratively remove outliers based on how many standard deviations they are from the mean,
    where the mean and standard deviation are recalculated after each cut.
    
    Parameters
    ----------
        data : ndarray
            Array of data that we want to remove outliers from
        cut : float, optional
            Number of standard deviations from the mean to be used for outlier rejection
        precision : float, optional
            Threshold for change in mean or standard deviation such that we stop iterating. The threshold is 
            determined by np.std(data)/precision. This means that a higher number for precision means a lower
            threshold (i.e. more iterations).
            
    Returns
    -------
        datamean : float
            Mean of the data after outliers have been removed.
        datastd : float
            Standard deviation of the data after outliers have been removed
        datamask : ndarray
            Boolean array indicating which values to keep or reject in data, same length as data.
    """
    
    stdcutoff = np.std(data)/precision
    
    meanlast = np.mean(data)
    stdlast = np.std(data)
    
    nstable = 0
    keepgoing = True
    
    while keepgoing:
        mask = abs(data - meanlast) < cut*stdlast
        if sum(mask) <=1:
            print('ERROR in iterstat: Number of events passing iterative cut is <= 1')
            print('Iteration not converging properly. Returning simple mean and std. No data will be cut.')
            
            meanthis = np.mean(data)
            stdthis = np.std(data)
            mask = np.ones(len(data),dtype=bool)
            break
        
        meanthis = np.mean(data[mask])
        stdthis = np.std(data[mask])
        
        if (abs(meanthis - meanlast) > stdcutoff) or (abs(stdthis - stdlast) > stdcutoff):
            nstable = 0
        else:
            nstable = nstable + 1
        if nstable >= 3:
            keepgoing = False
             
        meanlast = meanthis
        stdlast = stdthis
    
    datamean = meanthis
    datastd = stdthis
    datamask = mask
    
    return datamean,datastd,datamask

def pileupcut(traces, fs=625e3, outlieralgo="removeoutliers", nsig=2, removemeans=False):
    """
    Function to automatically cut out outliers of the optimum filter amplitudes of the inputted traces.
    
    Parameters
    ----------
        traces : ndarray
            2-dimensional array of traces to do cuts on
        fs : float, optional
            Digitization rate that the data was taken at
        outlieralgo : string, optional
            Which outlier algorithm to use. If set to "removeoutliers", uses the removeoutliers algorithm that
            removes data based on the skewness of the dataset. If set to "iterstat", uses the iterstat algorithm
            to remove data based on being outside a certain number of standard deviations from the mean
        nsig : float, optional
            If outlieralgo is "iterstat", this can be used to tune the number of standard deviations from the mean
            to cut outliers from the data when using iterstat on the optimum filter amplitudes. Default is 2.
        removemeans : boolean, optional
            Boolean flag on if the mean of each trace should be removed before doing the optimal filter (True) or
            if the means should not be removed (False). This is useful for dIdV traces, when we want to cut out
            pulses that have smaller amplitude than the dIdV overshoot. Default is False.
            
    Returns
    -------
        cpileup : ndarray
            Boolean array giving which indices to keep or throw out based on the outlier algorithm
            
    """
    
    nbin = len(traces[0])
    ind_trigger = round(nbin/2)
    time = 1.0/fs*(np.arange(1, nbin+1)-ind_trigger)
    lgc_b0 = time < 0.0
    
    # pulse shape
    tau_risepulse = 10.0e-6
    tau_fallpulse = 100.0e-6
    dummytemplate = (1.0-np.exp(-time/tau_risepulse))*np.exp(-time/tau_fallpulse)
    dummytemplate[lgc_b0]=0.0
    dummytemplate = dummytemplate/max(dummytemplate)
    
    # assume we just have white noise
    dummypsd = np.ones(nbin)
    
    if removemeans:
        mean = np.mean(traces, axis=1)
        traces -= mean[:, np.newaxis]
    
    amps = np.zeros(len(traces))
    
    #do optimum filter on all traces
    for itrace in range(0,len(traces)):
        amps[itrace] = ofamp(traces[itrace], dummytemplate, dummypsd, fs)[0]
        
    if outlieralgo=="removeoutliers":
        cpileup = removeoutliers(abs(amps))
    elif outlieralgo=="iterstat":
        cpileup = iterstat(abs(amps), cut=nsig, precision=10000.0)[2]
    else:
        raise ValueErrror("Unknown outlier algorithm inputted.")
        
    return cpileup

def slopecut(traces, outlieralgo="removeoutliers", nsig=2, is_didv=False, symmetrizeflag=False, sgfreq=100.0):
    """
    Function to automatically cut out outliers of the slopes of the inputted traces. Includes a routine that 
    attempts to symmetrize the distribution of slopes around zero, which is useful when the majority of traces 
    have a slope.
    
    Parameters
    ----------
        traces : ndarray
            2-dimensional array of traces to do cuts on
        outlieralgo : string, optional
            Which outlier algorithm to use. If set to "removeoutliers", uses the removeoutliers algorithm that
            removes data based on the skewness of the dataset. If set to "iterstat", uses the iterstat algorithm
            to remove data based on being outside a certain number of standard deviations from the mean
        nsig : float, optional
            If outlieralgo is "iterstat", this can be used to tune the number of standard deviations from the mean
            to cut outliers from the data when using iterstat on the slopes. Default is 2.
        is_didv : bool, optional
            Boolean flag on whether or not the trace is a dIdV curve
        symmetrizeflag : bool, optional
            Flag for whether or not the slopes should be forced to have an average value of zero.
            Should be used if most of the traces have a slope
        sgfreq : float, optional
            If is_didv is True, then the sgfreq is used to know where the flat parts of the traces should be
            
    Returns
    -------
        cslope : ndarray
            Boolean array giving which indices to keep or throw out based on the outlier algorithm
            
    """
    
    nbins = len(traces[0])
    tracebegin = np.zeros_like(amps)
    traceend = np.zeros_like(amps)
    
    # number of periods and bins in period to determine where to calculate slopes and baselines
    nperiods = np.floor((len(rawtraces[0])/fs)*sgfreq)
    binsinperiod = fs/sgfreq

    if is_didv:
        # try to use flat part of DIDV trace (assuming it's lined up with the start of a period)
        # should still work if it's not lined up
        if nperiods>1:
            sloperangebegin = range(int(binsinperiod/4), int(3*binsinperiod/8))
            sloperangeend = range(int((nperiods-1.0)*binsinperiod+binsinperiod/4), 
                                  int((nperiods-1.0)*binsinperiod+3*binsinperiod/8))
        else:
            sloperangebegin = range(int(binsinperiod/4), int(5*binsinperiod/16))
            sloperangeend = range(int(5*binsinperiod/16), int(3*binsinperiod/8))
    else:
        sloperangebegin = range(0, int(nbin/10))
        sloperangeend = range(int(9*nbin/10), nbin)
        
    tracebegin = np.mean(rawtraces[:, sloperangebegin], axis=1)
    traceend = np.mean(rawtraces[:, sloperangeend], axis=1)
    
    # now the slope cut to get rid of muon tails
    # first, create a symmetric distribution about zero slope to get rid of the biased results, 
    # but randomly cutting out events on biased side
    slopes = traceend - tracebegin

    # figure out which direction the slopes are usually
    slopesmean, slopesstd = iterstat(slopes[cpileup1inds], cut=2, precision=10000.0)[:-1]

    # if most slopes are positive, flip the sign of them so we can use the same code for both negative and positive slopes
    if slopesmean>0.0:
        slopes= -slopes

    # choose symmetric upper and lower bounds for histogram to make the middle bin centered on zero (since we want zero mean)
    histupr=max(slopes[cpileup1inds])
    histlwr=-histupr

    # specify number of bins in histogram (should be an odd number so that we have the middle bin centered on zero)
    nbins=int(np.sqrt(len(cpileup1inds)))
    if np.mod(nbins,2)==0:
        nbins+=1

    # create histogram, get number of events in each bin and where the bin edges are
    hist_num,bin_edges = np.histogram(slopes[cpileup1inds], bins=nbins, range=(histlwr,histupr))

    if len(hist_num)>2 and symmetrizeflag: # otherwise we cannot symmetrize the distribution
        # inititalize the cut that symmetrizes the slopes
        czeromeangaussianslope = np.zeros(len(cpileup1inds), dtype=bool)
        czeromeangaussianslope[slopes[cpileup1inds]>bin_edges[nbins//2]] = True

        slopestemp = slopes[cpileup1inds] # temporary variable to write less words

        # go through each bin and remove events until the bin number is symmetric
        for ibin in range(nbins/2,nbins-1):
            cslopesinbin = np.logical_and(slopestemp<bin_edges[nbins-ibin-1], slopestemp>=bin_edges[nbins-ibin-2])
            ntracesinthisbin = hist_num[nbins-ibin-2]
            ntracesinoppobin = hist_num[ibin+1]
            ntracestoremove = ntracesinthisbin-ntracesinoppobin
            if ntracestoremove>0.0:
                cslopesinbininds = np.where(cslopesinbin)[0]
                crandcut = random.sample(cslopesinbininds,ntracestoremove)
                cslopesinbin[crandcut] = False
            czeromeangaussianslope += cslopesinbin # update cut to include these events

        czeromeangaussianslopeinds = np.where(czeromeangaussianslope)[0]
    else:
        # don't do anything about the shape of the distrbution
        czeromeangaussianslopeinds = np.arange(nbins)

    # now get rid of outliers from the symmetrized distribution
    if outlieralgo=="removeoutliers":
        cslope = removeoutliers(slopes[czeromeangaussianslopeinds])
    elif outlieralgo=="iterstat":
        cslope = iterstat(slopes[czeromeangaussianslopeinds], cut=nsig, precision=10000.0)[2]
    else:
        raise ValueErrror("Unknown outlier algorithm inputted.")
        
    return cslope
    
def baselinecut(traces, outlieralgo="removeoutliers", nsig=2, is_didv=False, sgfreq=100.0):
    """
    Function to automatically cut out outliers of the baselines of the inputted traces.
    
    Parameters
    ----------
        traces : ndarray
            2-dimensional array of traces to do cuts on
        outlieralgo : string, optional
            Which outlier algorithm to use. If set to "removeoutliers", uses the removeoutliers algorithm that
            removes data based on the skewness of the dataset. If set to "iterstat", uses the iterstat algorithm
            to remove data based on being outside a certain number of standard deviations from the mean
        nsig : float, optional
            If outlieralgo is "iterstat", this can be used to tune the number of standard deviations from the mean
            to cut outliers from the data when using iterstat on the baselines. Default is 2.
        is_didv : bool, optional
            Boolean flag on whether or not the trace is a dIdV curve
        sgfreq : float, optional
            If is_didv is True, then the sgfreq is used to know where the flat parts of the traces should be
            
    Returns
    -------
        cbaseline : ndarray
            Boolean array giving which indices to keep or throw out based on the outlier algorithm
            
    """
    
    nbins = len(traces[0])
    tracebegin = np.zeros_like(amps)
    
    # number of periods and bins in period to determine where to calculate slopes and baselines
    nperiods = np.floor((len(rawtraces[0])/fs)*sgfreq)
    binsinperiod = fs/sgfreq

    if is_didv:
        # try to use flat part of DIDV trace (assuming it's lined up with the start of a period)
        # should still work if it's not lined up
        if nperiods>1:
            sloperangebegin = range(int(binsinperiod/4), int(3*binsinperiod/8))
        else:
            sloperangebegin = range(int(binsinperiod/4), int(5*binsinperiod/16))
    else:
        sloperangebegin = range(0, int(nbin/10))
        
    tracebegin = np.mean(rawtraces[:, sloperangebegin], axis=1)
    
    # baseline cut
    if outlieralgo=="removeoutliers":
        cbaseline = removeoutliers(tracebegin[cslopeinds])
    elif outlieralgo=="iterstat":
        cbaseline = iterstat(tracebegin[cslopeinds], cut=nsig, precision=10000.0)[2]
    else:
        raise ValueErrror("Unknown outlier algorithm inputted.")
    
    return cbaseline

def chi2cut(traces, outlieralgo="iterstat", nsig=2):
    """
    Function to automatically cut out outliers of the baselines of the inputted traces.
    
    Parameters
    ----------
        traces : ndarray
            2-dimensional array of traces to do cuts on
        outlieralgo : string, optional
            Which outlier algorithm to use. If set to "removeoutliers", uses the removeoutliers algorithm that
            removes data based on the skewness of the dataset. If set to "iterstat", uses the iterstat algorithm
            to remove data based on being outside a certain number of standard deviations from the mean
        nsig : float, optional
            If outlieralgo is "iterstat", this can be used to tune the number of standard deviations from the mean
            to cut outliers from the data when using iterstat on the Chi2s. Default is 2.
            
    Returns
    -------
        cchi2 : ndarray
            Boolean array giving which indices to keep or throw out based on the outlier algorithm
            
    """
    
    nbin = len(traces[0])
    ind_trigger = round(nbin/2)
    time = 1.0/fs*(np.arange(1, nbin+1)-ind_trigger)
    lgc_b0 = time < 0.0
    
    # pulse shape
    tau_risepulse = 10.0e-6
    tau_fallpulse = 100.0e-6
    dummytemplate = (1.0-np.exp(-time/tau_risepulse))*np.exp(-time/tau_fallpulse)
    dummytemplate[lgc_b0]=0.0
    dummytemplate = dummytemplate/max(dummytemplate)
    
    # assume we just have white noise
    dummypsd = np.ones(nbin)
    
    chi2 = np.zeros(len(traces))
    
    # First do optimum filter on all traces without mean subtracted
    for itrace in range(0,len(traces)):
        chi2[itrace] = ofamp(traces[itrace], dummytemplate, dummypsd, fs)[-1]
        
    if outlieralgo=="removeoutliers":
        cchi2 = removeoutliers(chi2)
    elif outlieralgo=="iterstat":
        cchi2 = iterstat(chi2, cut=nsig, precision=10000.0)[2]
    else:
        raise ValueErrror("Unknown outlier algorithm inputted.")
        
    return cchi2

def autocuts(traces, fs=625e3, is_didv=False, sgfreq=200.0, symmetrizeflag=False, outlieralgo="removeoutliers",
             lgcpileup1=True, lgcslope=True, lgcbaseline=True, lgcpileup2=True, lgcchi2=True,
             nsigpileup1=2, nsigslope=2, nsigbaseline=2, nsigpileup2=2, nsigchi2=3):
    """
    Function to automatically cut out bad traces based on the optimum filter amplitude, slope, baseline, and chi^2
    of the traces.
    
    Parameters
    ----------
        traces : ndarray
            2-dimensional array of traces to do cuts on
        fs : float, optional
            Sample rate that the data was taken at
        is_didv : bool, optional
            Boolean flag on whether or not the trace is a dIdV curve
        sgfreq : float, optional
            If is_didv is True, then the sgfreq is used to know where the flat parts of the traces should be
        symmetrizeflag : bool, optional
            Flag for whether or not the slopes should be forced to have an average value of zero.
            Should be used if most of the traces have a slope
        outlieralgo : string, optional
            Which outlier algorithm to use. If set to "removeoutliers", uses the removeoutliers algorithm that
            removes data based on the skewness of the dataset. If set to "iterstat", uses the iterstat algorithm
            to remove data based on being outside a certain number of standard deviations from the mean
        lgcpileup1 : boolean, optional
            Boolean value on whether or not do the pileup1 cut (this is the initial pileup cut
            that is always done whether or not we have dIdV data). Default is True.
        lgcslope : boolean, optional
            Boolean value on whether or not do the slope cut. Default is True.
        lgcbaseline : boolean, optional
            Boolean value on whether or not do the baseline cut. Default is True.
        lgcpileup2 : boolean, optional
            Boolean value on whether or not do the pileup2 cut (this cut is only done when is_didv is
            also True). Default is True.
        lgcchi2 : boolean, optional
            Boolean value on whether or not do the chi2 cut. Default is True.
        nsigpileup1 : float, optional
            If outlieralgo is "iterstat", this can be used to tune the number of standard deviations from the mean
            to cut outliers from the data when using iterstat on the optimum filter amplitudes. Default is 2.
        nsigslope : float, optional
            If outlieralgo is "iterstat", this can be used to tune the number of standard deviations from the mean
            to cut outliers from the data when using iterstat on the slopes. Default is 2.
        nsigbaseline : float, optional
            If outlieralgo is "iterstat", this can be used to tune the number of standard deviations from the mean
            to cut outliers from the data when using iterstat on the baselines. Default is 2.
        nsigpileup2 : float, optional
            If outlieralgo is "iterstat", this can be used to tune the number of standard deviations from the mean
            to cut outliers from the data when using iterstat on the optimum filter amplitudes after the mean
            has been subtracted. (only used if is_didv is True). Default is 2.
        nsigchi2 : float, optional
            This can be used to tune the number of standard deviations from the mean to cut outliers from the data
            when using iterstat on the chi^2 values. Default is 3. This is always used, as iterstat is always used
            for the chi^2 cut.
            
    Returns
    -------
        ctot : ndarray
            Boolean array giving which indices to keep or throw out based on the autocuts algorithm
            
    """
    
    # pileup cut
    if lgcpileup1:
        cpileup1 = pileupcut(traces, fs=fs, outlieralgo=outlieralgo, nsig=nsigpileup1)
        cpileup1inds = np.where(cpileup1)[0]
    else:
        cpileup1inds = np.arange(len(traces))
    
    #slope cut
    if lgcslope:
        cslope = slopecut(traces, outlieralgo=outlieralgo, nsig=nsigslope, is_didv=is_didv, 
                          symmetrizeflag=symmetrizeflag, sgfreq=sgfreq)
    else:
        cslope = np.ones(cpileup1inds.shape, dtype=bool)
    cslopeinds = cpileup1inds[cslope]

    # baseline cut
    if lgcbaseline:
        cbaseline = baselinecut(traces, outlieralgo=outlieralgo, nsig=nsigbaseline, is_didv=is_didv, 
                                sgfreq=sgfreq)
    else:
        cbaseline = np.ones(cslopeinds.shape, dtype=bool)
    cbaselineinds = cslopeinds[cbaseline]

    # do a pileup cut on the mean subtracted data if this is a dIdV, so that we remove pulses
    # that are smaller than the dIdV peaks
    if lgcpileup2 and is_didv:
        cpileup2 = pileupcut(traces, outlieralgo=outlieralgo, nsig=nsigpileup2, removemeans=True)
    else:
        cpileup2 = np.ones(cbaselineinds.shape, dtype=bool)
    cpileup2inds = cbaselineinds[cpileup2]

    #general chi2 cut, this should use iterstat, as there shouldn't be a tail
    if lgcchi2:
        cchi2 = chi2cut(traces, fs=fs, outlieralgo="iterstat", nsig=nsigchi2)
    else:
        cchi2 = np.ones(cpileup2inds.shape, dtype=bool)
    cchi2inds = cpileup2inds[cchi2]

    # convert total cut to logical array
    ctot = np.zeros(len(traces),dtype=bool)
    ctot[cchi2inds] = True
        
    return ctot
