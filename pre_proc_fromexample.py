#!/usr/bin/env python
# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
=========
fMRI: FSL
=========

A workflow that uses fsl to perform a first level analysis on the nipype
tutorial data set::

    python fmri_fsl.py


First tell python where to find the appropriate functions.
"""

import os                                    # system functions

import nipype.interfaces.io as nio           # Data i/o
import nipype.interfaces.fsl as fsl          # fsl
import nipype.interfaces.utility as util     # utility
import nipype.pipeline.engine as pe          # pypeline engine
import nipype.algorithms.modelgen as model   # model generation
import nipype.algorithms.rapidart as ra      # artifact detection



"""
Preliminaries
-------------

Setup any package specific configuration. The output file format for FSL
routines is being set to compressed NIFTI.
"""

fsl.FSLCommand.set_default_output_type('NIFTI_GZ')

"""
Setting up workflows
--------------------

In this tutorial we will be setting up a hierarchical workflow for fsl
analysis. This will demonstrate how pre-defined workflows can be setup and
shared across users, projects and labs.


Setup preprocessing workflow
----------------------------

This is a generic fsl feat preprocessing workflow encompassing skull stripping,
motion correction and smoothing operations.

"""

preproc = pe.Workflow(name='preproc')

"""
Set up a node to define all inputs required for the preprocessing workflow
"""

inputnode = pe.Node(interface=util.IdentityInterface(fields=['func',
                                                             'struct',]),
                    name='inputspec')

"""
Convert functional images to float representation. Since there can be more than
one functional run we use a MapNode to convert each run.
"""

img2float = pe.MapNode(interface=fsl.ImageMaths(out_data_type='float',
                                             op_string = '',
                                             suffix='_dtype'),
                       iterfield=['in_file'],
                       name='img2float')
preproc.connect(inputnode, 'func', img2float, 'in_file')

"""
Extract the middle volume of the first run as the reference
"""

extract_ref = pe.Node(interface=fsl.ExtractROI(t_size=1),
                      name = 'extractref')

"""
Define a function to pick the first file from a list of files
"""

def pickfirst(files):
    if isinstance(files, list):
        return files[0]
    else:
        return files

preproc.connect(img2float, ('out_file', pickfirst), extract_ref, 'in_file')

"""
Define a function to return the 1 based index of the middle volume
"""

def getmiddlevolume(func):
    from nibabel import load
    funcfile = func
    if isinstance(func, list):
        funcfile = func[0]
    _,_,_,timepoints = load(funcfile).get_shape()
    return (timepoints/2)-1

preproc.connect(inputnode, ('func', getmiddlevolume), extract_ref, 't_min')

"""
Realign the functional runs to the middle volume of the first run
"""

motion_correct = pe.MapNode(interface=fsl.MCFLIRT(save_mats = True,
                                                  save_plots = True),
                            name='realign',
                            iterfield = ['in_file'])
preproc.connect(img2float, 'out_file', motion_correct, 'in_file')
preproc.connect(extract_ref, 'roi_file', motion_correct, 'ref_file')


"""
Plot the estimated motion parameters
"""

plot_motion = pe.MapNode(interface=fsl.PlotMotionParams(in_source='fsl'),
                        name='plot_motion',
                        iterfield=['in_file'])
plot_motion.iterables = ('plot_type', ['rotations', 'translations'])
preproc.connect(motion_correct, 'par_file', plot_motion, 'in_file')

"""
Extract the mean volume of the first functional run
"""

meanfunc = pe.Node(interface=fsl.ImageMaths(op_string = '-Tmean',
                                            suffix='_mean'),
                   name='meanfunc')
preproc.connect(motion_correct, ('out_file', pickfirst), meanfunc, 'in_file')

"""
Strip the skull from the mean functional to generate a mask
"""

meanfuncmask = pe.Node(interface=fsl.BET(mask = True,
                                         no_output=True,
                                         frac = 0.3),
                       name = 'meanfuncmask')
preproc.connect(meanfunc, 'out_file', meanfuncmask, 'in_file')

"""
Mask the functional runs with the extracted mask
"""

maskfunc = pe.MapNode(interface=fsl.ImageMaths(suffix='_bet',
                                               op_string='-mas'),
                      iterfield=['in_file'],
                      name = 'maskfunc')
preproc.connect(motion_correct, 'out_file', maskfunc, 'in_file')
preproc.connect(meanfuncmask, 'mask_file', maskfunc, 'in_file2')


"""
Determine the 2nd and 98th percentile intensities of each functional run
"""

getthresh = pe.MapNode(interface=fsl.ImageStats(op_string='-p 2 -p 98'),
                       iterfield = ['in_file'],
                       name='getthreshold')
preproc.connect(maskfunc, 'out_file', getthresh, 'in_file')


"""
Threshold the first run of the functional data at 10% of the 98th percentile
"""

threshold = pe.Node(interface=fsl.ImageMaths(out_data_type='char',
                                             suffix='_thresh'),
                    name='threshold')
preproc.connect(maskfunc, ('out_file', pickfirst), threshold, 'in_file')

"""
Define a function to get 10% of the intensity
"""

def getthreshop(thresh):
    return '-thr %.10f -Tmin -bin'%(0.1*thresh[0][1])
preproc.connect(getthresh, ('out_stat', getthreshop), threshold, 'op_string')

"""
Determine the median value of the functional runs using the mask
"""

medianval = pe.MapNode(interface=fsl.ImageStats(op_string='-k %s -p 50'),
                       iterfield = ['in_file'],
                       name='medianval')
preproc.connect(motion_correct, 'out_file', medianval, 'in_file')
preproc.connect(threshold, 'out_file', medianval, 'mask_file')

"""
Dilate the mask
"""

dilatemask = pe.Node(interface=fsl.ImageMaths(suffix='_dil',
                                              op_string='-dilF'),
                     name='dilatemask')
preproc.connect(threshold, 'out_file', dilatemask, 'in_file')

"""
Mask the motion corrected functional runs with the dilated mask
"""

maskfunc2 = pe.MapNode(interface=fsl.ImageMaths(suffix='_mask',
                                                op_string='-mas'),
                       iterfield=['in_file'],
                       name='maskfunc2')
preproc.connect(motion_correct, 'out_file', maskfunc2, 'in_file')
preproc.connect(dilatemask, 'out_file', maskfunc2, 'in_file2')

"""
Determine the mean image from each functional run
"""

meanfunc2 = pe.MapNode(interface=fsl.ImageMaths(op_string='-Tmean',
                                                suffix='_mean'),
                       iterfield=['in_file'],
                       name='meanfunc2')
preproc.connect(maskfunc2, 'out_file', meanfunc2, 'in_file')

"""
Merge the median values with the mean functional images into a coupled list
"""

mergenode = pe.Node(interface=util.Merge(2, axis='hstack'),
                    name='merge')
#preproc.connect(meanfunc2,'out_file', mergenode, 'in1')
#preproc.connect(medianval,'out_stat', mergenode, 'in2')


"""
Smooth each run using SUSAN with the brightness threshold set to 75% of the
median value for each run and a mask constituting the mean functional
"""

smooth = pe.MapNode(interface=fsl.SUSAN(),
                    iterfield=['in_file', 'brightness_threshold','usans'],
                    name='smooth')

"""
Define a function to get the brightness threshold for SUSAN
"""

def getbtthresh(medianvals):
    return [0.75*val for val in medianvals]

def getusans(x):
    return [[tuple([val[0],0.75*val[1]])] for val in x]

#preproc.connect(maskfunc2, 'out_file', smooth, 'in_file')
#preproc.connect(medianval, ('out_stat', getbtthresh), smooth, 'brightness_threshold')
#preproc.connect(mergenode, ('out', getusans), smooth, 'usans')

"""
Mask the smoothed data with the dilated mask
"""

maskfunc3 = pe.MapNode(interface=fsl.ImageMaths(suffix='_mask',
                                                op_string='-mas'),
                       iterfield=['in_file'],
                       name='maskfunc3')
#preproc.connect(smooth, 'smoothed_file', maskfunc3, 'in_file')
#preproc.connect(dilatemask, 'out_file', maskfunc3, 'in_file2')

"""
Scale each volume of the run so that the median value of the run is set to 10000
"""

intnorm = pe.MapNode(interface=fsl.ImageMaths(suffix='_intnorm'),
                     iterfield=['in_file','op_string'],
                     name='intnorm')
#preproc.connect(maskfunc2, 'out_file', intnorm, 'in_file')

"""
Define a function to get the scaling factor for intensity normalization
"""

"""
Perform temporal highpass filtering on the data
"""

highpass = pe.MapNode(interface=fsl.ImageMaths(suffix='_tempfilt'),
                      iterfield=['in_file'],
                      name='highpass')
#preproc.connect(intnorm, 'out_file', highpass, 'in_file')

"""
Generate a mean functional image from the first run
"""

meanfunc3 = pe.MapNode(interface=fsl.ImageMaths(op_string='-Tmean',
                                                suffix='_mean'),
                       iterfield=['in_file'],
                       name='meanfunc3')
preproc.connect(mask_func2, 'out_file', meanfunc3, 'in_file')

"""
Strip the structural image and coregister the mean functional image to the
structural image
"""

nosestrip = pe.Node(interface=fsl.BET(frac=0.3),
                    name = 'nosestrip')
skullstrip = pe.Node(interface=fsl.BET(mask = True),
                     name = 'stripstruct')

coregister = pe.Node(interface=fsl.FLIRT(dof=6),
                     name = 'coregister')

"""
Use :class:`nipype.algorithms.rapidart` to determine which of the
images in the functional series are outliers based on deviations in
intensity and/or movement.
"""

art = pe.MapNode(interface=ra.ArtifactDetect(use_differences = [True, False],
                                             use_norm = True,
                                             norm_threshold = 1,
                                             zintensity_threshold = 3,
                                             parameter_source = 'FSL',
                                             mask_type = 'file'),
                 iterfield=['realigned_files', 'realignment_parameters'],
                 name="art")


preproc.connect([(inputnode, nosestrip,[('struct','in_file')]),
                 (nosestrip, skullstrip, [('out_file','in_file')]),
                 (skullstrip, coregister,[('out_file','in_file')]),
                 (meanfunc2, coregister,[(('out_file',pickfirst),'reference')]),
                 (motion_correct, art, [('par_file','realignment_parameters')]),
                 (maskfunc2, art, [('out_file','realigned_files')]),
                 (dilatemask, art, [('out_file', 'mask_file')]),
                 ])
