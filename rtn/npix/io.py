# -*- coding: utf-8 -*-
"""
Created on Fri May  3 16:30:50 2019

@author: Maxime Beau, Hausser lab, University College London

Input/output utilitaries to deal with Neuropixels files.
"""

import psutil
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .utils import phyColorsDic, seabornColorsDic, DistinctColors20, DistinctColors15, mark_dict,\
                    npa, sign, minus_is_1, thresh, smooth, \
                    _as_array, _unique, _index_of

#%% raw data extraction

def extract_rawChunk(bp, times, channels=np.arange(384), fs=30000, ampFactor=500, Nchans=385, syncChan=384, save=0, ret=1):
    '''Function to extract a chunk of raw data on a given range of channels on a given time window.
    ## PARAMETERS
    - bp: binary path (files must ends in .bin, typically ap.bin)
    - times: list of boundaries of the time window, in seconds [t1, t2]. If 'all', whole recording.
    - channels (default: np.arange(0, 385)): list of channels of interest, in 0 indexed integers [c1, c2, c3...]
    - fs (default 30000): sampling rate
    - ampFactor (default 500): gain factor of recording (can be different for LFP and AP, check SpikeGLX/OpenEphys)
    - Nchans (default 385): total number of channels on the probe, including sync channel (3A: 385)
    - syncChan: sync channel, 0 indexed(3A: 384)
    - save (default 0): save the raw chunk in the bdp directory as '{bdp}_t1-t2_c1-c2.npy'
    
    ## RETURNS
    rawChunk: numpy array of shape ((c2-c1), (t2-t1)*fs).
    rawChunk[0,:] is channel 0; rawChunk[1,:] is channel 1, etc.
    '''
    
    assert len(times)==2
    channels = np.array(channels, dtype=np.int16); assert np.all(channels<=(Nchans-1))
    assert bp[-4:]=='.bin'
    bn = bp.split('/')[-1] # binary name
    dp = bp[:-len(bn)-1] # data path
    rcn = '{}_t{}-{}_ch{}-{}.npy'.format(bn, times[0], times[1], channels[0], channels[-1]) # raw chunk name
    rcp = dp+'/'+rcn
    
    
    if os.path.isfile(rcp):
        return np.load(rcp)
    
    # Check that available memory is high enough to load the raw chunk
    vmem=dict(psutil.virtual_memory()._asdict())
    chunkSize = fs*385*2*(times[1]-times[0])
    print('Used RAM: {0:.1f}% ({1:.2f}GB total).'.format(vmem['used']*100/vmem['total'], vmem['total']/1024/1024/1024))
    print('Chunk size:{0:.3f}MB. Available RAM: {1:.3f}MB.'.format(chunkSize/1024/1024, vmem['available']/1024/1024))
    if chunkSize>0.9*vmem['available']:
        print('WARNING you are trying to load {0:.3f}MB into RAM but have only {1:.3f}MB available.\
              Pick less channels or a smaller time chunk.'.format(chunkSize/1024/1024, vmem['available']/1024/1024))
        return
    
    # Get chunk from binary file
    with open(bp, 'rb') as f_src:
        # each sample for each channel is encoded on 16 bits = 2 bytes: samples*Nchannels*2.
        t1, t2 = times
        byte1 = int(t1*fs*Nchans*2)
        byte2 = int(t2*fs*Nchans*2)
        bytesRange = byte2-byte1
        
        f_src.seek(byte1)
        
        bData = f_src.read(bytesRange)
    
    # Decode binary data
    rc = np.frombuffer(bData, dtype=np.int16) # 16bits decoding
    rc = rc*(1.2e6/2**10/ampFactor) # convert into uV
    rc = rc.reshape((int(t2*fs-t1*fs), Nchans)).T
    rc = rc[channels, :] # get the right channels range
    if syncChan in channels:
        print('WARNING: you also extracted the sync channel ({}) as a recording channel, it will be meaningless.'.format(syncChan))
    
    # Center channels individually
    offsets = np.mean(rc, axis=1)
    print('Channels are offset by {}uV on average!'.format(np.mean(offsets)))
    offsets = np.tile(offsets[:,np.newaxis], (1, rc.shape[1]))
    rc-=offsets
    
    if save: # sync chan saved in extract_syncChan
        np.save(rcp, rc)
    
    if ret:
        return rc
    else:
        return

def extract_syncChan(bp, syncChan=384, fs=30000, ampFactor=500, Nchans=385, save=0):
    ''' Extracts the 16 'square signals' corresponding to the 16 pins input to the Neuropixels FPGA board
    ### PARAMETERS
    - bp: binary path (files must ends in .bin, typically ap.bin)
    - synchan (default 384): 0-indexed sync channel
    - times: list of boundaries of the time window, in seconds [t1, t2]. If 'all', whole recording.
    - fs (default 30000): sampling rate
    - ampFactor (default 500): gain factor of recording (can be different for LFP and AP, check SpikeGLX/OpenEphys)
    - Nchans (default 385): total number of channels on the probe (3A: 385, )
    - save (default 0): save the raw chunk in the bdp directory as '{bdp}_t1-t2_c1-c2.npy'
    
    ## RETURNS
    sync channel: 16*Nsamples numpy binary array
    (@ 30kHz of bp is the AP binary file, use fs=25000 if you want to use the LF file)
    '''
    
    assert bp[-4:]=='.bin'
    bn = bp.split('/')[-1] # binary name
    dp = bp[:-len(bn)-1] # data path
    rcn = '{}_sync.npy'.format(bn) # raw chunk name
    rcp = dp+'/'+rcn
    if os.path.isfile(rcp):
        return np.load(rcp)
    
    # Get sync channel, formatted as an string of Nsamples bytes
    sc=b''
    with open(bp, 'rb') as f_src:
        # each sample for each channel is encoded on 16 bits = 2 bytes: samples*Nchannels*2.
        i=30000
        while i<60000:
            print('{0:.3f}%...'.format(100*i/(os.path.getsize(bp)/(Nchans*2))))
            f_src.seek(int(i*Nchans+syncChan)*2) # get to 385*i+384 channels,
            b = f_src.read(2) # then read 2 bytes = 16bits
            if not b:
                break
            sc+=b
            print(i)
            print(len(sc)/4)
            i+=1
            
    # turn it into bits
    sc = np.frombuffer(sc, dtype=np.uint8) # bytes to uint8
    sc = np.unpackbits(sc) # uint8 to binary bits
    Nsamples=int(len(sc)/16)
    sc = sc.reshape((Nsamples, 16)).T

    if save:
        np.save(rcp, sc)
        
    return sc

def extract_syncEvents(bp, sign=1, syncChan=384, times='all', fs=30000, ampFactor=500, Nchans=385, save=0):
    
    # Get sync chan
    sc = extract_syncChan(bp, syncChan, times, fs, ampFactor, Nchans, save)
    
    # threshold syncchan
    events = thresh(sc, 0.5, sgn=sign)
    
    return events


def plot_raw(bp, times, channels=np.arange(385), offset=450, fs=30000, ampFactor=500, Nchans=385, save=0, savePlot=0):
    '''
    ## PARAMETERS
    - bp: binary path (files must ends in .bin, typically ap.bin)
    - times: list of boundaries of the time window, in seconds [t1, t2]. If 'all', whole recording.
    - channels (default: np.arange(0, 385)): list of channels of interest, in 0 indexed integers [c1, c2, c3...]
    - offset: graphical offset between channels, in uV
    - fs (default 30000): sampling rate
    - ampFactor (default 500): gain factor of recording (can be different for LFP and AP, check SpikeGLX/OpenEphys)
    - Nchans (default 385): total number of channels on the probe (3A: 385, )
    - save (default 0): save the raw chunk in the bdp directory as '{bdp}_t1-t2_c1-c2.npy'
    
    ## RETURNS
    fig: a matplotlib figure with channel 0 being plotted at the bottom and channel 384 at the top.
    
    
    '''
    
    # Get data
    rawChunk = extract_rawChunk(bp, times, channels, fs, ampFactor, Nchans, save)

    # Offset data
    plt_offsets = np.arange(0, len(channels)*offset, offset)
    plt_offsets = np.tile(plt_offsets[:,np.newaxis], (1, rawChunk.shape[1]))
    rawChunk+=plt_offsets
    
    # Plot data
    fig, ax = plt.subplots()
    y_subticks = np.arange(50, offset/2, 50)
    y_ticks=[plt_offsets[:,0]]
    for i in y_subticks:
        y_ticks+=[plt_offsets[:,0]-i, plt_offsets[:,0]+i] 
    y_ticks = np.sort(npa(y_ticks).flatten())
    y_labels = npa([(y_subticks[::-1]*-1).tolist()+['#{}'.format(channels[i])]+y_subticks.tolist() for i in range(len(channels))]).flatten()
    
    t=np.tile(np.arange(rawChunk.shape[1])*1000./fs, (rawChunk.shape[0], 1))
    for i in np.arange(rawChunk.shape[0]):
        y=i*offset
        ax.plot([0, t[0,-1]], [y, y], color=(0.5, 0.5, 0.5), linestyle='--', linewidth=1)
    ax.plot(t.T, rawChunk.T, linewidth=1)
    ax.set_xlabel('Time (ms)')
    ax.set_ylabel('Extracellular potential (uV)')
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels)
    
    return fig





import pandas as pd
import numpy as np
import os
from importlib.machinery import SourceFileLoader


bs_utilities = SourceFileLoader("bs", "/home/brandon/PycharmProjects/pythonUtilities/general.py").load_module()

def unpackbits(x,num_bits = 16):
    '''
    unpacks numbers in bits.
    '''
    xshape = list(x.shape)
    x = x.reshape([-1,1])
    to_and = 2**np.arange(num_bits).reshape([1,num_bits])
    return (x & to_and).astype(bool).astype(int).reshape(xshape + [num_bits])

def map_binary(fname, nchannels=385, dtype=np.int16, offset=0, mode='r', nsamples=None, transpose=False):
    '''
    dat = map_binary(fname,nchannels,dtype=np.int16,mode = 'r',nsamples = None)

    Memory maps a binary file to numpy array.
        Inputs:
            fname           : path to the file
            nchannels       : number of channels
            dtype (int16)   : datatype
            mode ('r')      : mode to open file ('w' - overwrites/creates; 'a' - allows overwriting samples)
            nsamples (None) : number of samples (if None - gets nsamples from the filesize, nchannels and dtype)
        Outputs:
            data            : numpy.memmap object (nchannels x nsamples array)
    See also: map_spikeglx, numpy.memmap
    
        Usage:
    Plot a chunk of data:
        dat = map_binary(filename, nchannels = 385)
        chunk = dat[:-150,3000:6000]
    
        import pylab as plt
        offset = 40
        fig = plt.figure(figsize=(10,13)); fig.add_axes([0,0,1,1])
        plt.plot(chunk.T - np.nanmedian(chunk,axis = 1) + offset * np.arange(chunk.shape[0]), lw = 0.5 ,color = 'k');
        plt.axis('tight');plt.axis('off');

    '''
    dt = np.dtype(dtype)
    if not os.path.exists(fname):
        if not mode == 'w':
            raise (ValueError('File ' + fname + ' does not exist?'))
        else:
            print('Does not exist, will create [{0}].'.format(fname))
            if not os.path.isdir(os.path.dirname(fname)):
                os.makedirs(os.path.dirname(fname))
    if nsamples is None:
        if not os.path.exists(fname):
            raise (ValueError('Need nsamples to create new file.'))
        # Get the number of samples from the file size
        nsamples = os.path.getsize(fname) / (nchannels * dt.itemsize)

    ret = np.memmap(fname,
                    mode=mode,
                    dtype=dt,
                    shape=(int(nsamples), int(nchannels)))

    if transpose:
        ret = ret.transpose([1, 0])
    return ret

def unpack_npix_sync(syncdat,srate=1,output_binary = False):
    '''Unpacks neuropixels phase external input data
    events = unpack_npix3a_sync(trigger_data_channel)
        Inputs:
            syncdat               : trigger data channel to unpack (pass the last channel of the memory mapped file)
            srate (1)             : sampling rate of the data; to convert to time - meta['imSampRate']
            output_binary (False) : outputs the unpacked signal
        Outputs
            events        : dictionary of events. the keys are the channel number, the items the sample times of the events.
    
        Usage:
    Load and get trigger times in seconds:
        dat,meta = load_spikeglx('test3a.imec.lf.bin')
        srate = meta['imSampRate']
        onsets,offsets = unpack_npix_sync(dat[:,-1],srate);
    Plot events:
        plt.figure(figsize = [10,4])
        for ichan,times in onsets.items():
            plt.vlines(times,ichan,ichan+.8,linewidth = 0.5)
        plt.ylabel('Sync channel number'); plt.xlabel('time (s)')
    '''
    dd = unpackbits(syncdat.flatten(),16)
    mult = 1
    if output_binary:
        return dd
    sync_idx_onset = np.where(mult*np.diff(dd,axis = 0)>0)
    sync_idx_offset = np.where(mult*np.diff(dd,axis = 0)<0)
    onsets = {}
    offsets = {}
    for ichan in np.unique(sync_idx_onset[1]):
        onsets[ichan] = sync_idx_onset[0][
            sync_idx_onset[1] == ichan]/srate
    for ichan in np.unique(sync_idx_offset[1]):
        offsets[ichan] = sync_idx_offset[0][
            sync_idx_offset[1] == ichan]/srate
    return onsets,offsets

def read_spikeglx_meta(metafile):
    '''
    Read spikeGLX metadata file.
    '''
    with open(metafile, 'r') as f:
        meta = {}
        for ln in f.readlines():
            tmp = ln.split('=')
            k, val = tmp
            k = k.strip()
            val = val.strip('\r\n')
            if '~' in k:
                meta[k] = val.strip('(').strip(')').split(')(')
            else:
                try:  # is it numeric?
                    meta[k] = float(val)
                except:
                    try:
                        meta[k] = float(val)
                    except:
                        meta[k] = val
    # Set the sample rate depending on the recording mode

    meta['sRateHz'] = meta[meta['typeThis'][:2] + 'SampRate']
    if meta['typeThis'] == 'imec':
        meta['sRateHz'] = meta['imSampRate']
    return meta


def load_spikeglx_binary(fname, dtype=np.int16):
    '''
    data,meta = load_spikeglx_binary(fname,nchannels)

    Memory maps a spikeGLX binary file to numpy array.

    Inputs:
        fname           : path to the file
    Outputs:
        data            : numpy.memmap object (nchannels x nsamples array)
        meta            : meta data from spikeGLX
    '''
    name = os.path.splitext(fname)[0]
    ext = '.meta'

    metafile = name + ext
    if not os.path.isfile(metafile):
        raise (ValueError('File not found: ' + metafile))
    meta = read_spikeglx_meta(metafile)
    nchans = meta['nSavedChans']
    return map_binary(fname, nchans, dtype=np.int16, mode='r'), meta



def neuropixel_binary_to_steps(np_df):  # overwrites the input df
    np_df['wheel'] = bs_utilities.raw_encoder_to_steps(np_df[0], np_df[1])
    np_df.drop(columns=[0, 1], inplace=True)
    np_df['left'] = bs_utilities.raw_encoder_to_steps(np_df[3], np_df[2])
    np_df.drop(columns=[2, 3], inplace=True)
    np_df['right'] = bs_utilities.raw_encoder_to_steps(np_df[4], np_df[5])
    np_df.drop(columns=[4, 5], inplace=True)
    np_df['reward'] = np_df[6] - 1
    np_df.reward *= np_df.reward
    np_df.drop(columns=[6], inplace=True)
    np_df = np_df.where(np_df.wheel+np_df.right+np_df.left+np_df.reward != 0)
    np_df.dropna(inplace=True)
    np_df = np_df.astype('int')
    np_df['us'] = np_df.index
    np_df.us = np_df.us.diff()
    return np_df



filename = '/home/brandon/Documents/DATA/neuropixels/BS041.track1.run2_g0/BS041.track1.run2_g0_t0.imec0.ap.bin'
dat,meta = load_spikeglx_binary(filename)
srate = meta['imSampRate']
# unpack to binary
binsync = unpack_npix_sync(dat[:,-1],srate, output_binary=True)
nsyncchannels = binsync.shape[1]
time = np.arange(binsync.shape[0])/srate
df = pd.DataFrame(binsync[:,0:7], index=time)
del time, binsync

df = neuropixel_binary_to_steps(df)
