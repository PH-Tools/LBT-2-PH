#
# LBT2PH: A Plugin for creating Passive House Planning Package (PHPP) models from LadybugTools. Created by blgdtyp, llc
# 
# This component is part of the PH-Tools toolkit <https://github.com/PH-Tools>.
# 
# Copyright (c) 2020, bldgtyp, llc <phtools@bldgtyp.com> 
# LBT2PH is free software; you can redistribute it and/or modify 
# it under the terms of the GNU General Public License as published 
# by the Free Software Foundation; either version 3 of the License, 
# or (at your option) any later version. 
# 
# LBT2PH is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of 
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the 
# GNU General Public License for more details.
# 
# For a copy of the GNU General Public License
# see <http://www.gnu.org/licenses/>.
# 
# @license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
#
"""
Use this component AFTER a Honeybee 'Aperture' component. This will pull data from  the Rhino scene (names, constructions, etc) where relevant.
-
EM March 1, 2021
    Args:
        apertures: (list> The HB Aperture objects from a 'Aperture' component
        frames_: (list) Optional. PHPP Frame Object or Objects
        glazings_: (list) Optional. PHPP Glazing Object or Objects
        installs_: (list) Optional. An optional entry for user-defined 
            Install Conditions (1|0) for each window edge (1=Apply Psi-Install, 
            0=Don't apply Psi-Install). Either pass in a single number which will 
            be used for all edges, or a list of 4 numbers (left, right, bottom, 
            top) - one for each edge.
        install_depth_: (list) Optional. Default=0.100m (4") The distance (m) that 
            that the glazing surface is set 'back' into the wall. Value should be 
            measured from the face of glazing to face of wall finish.
    Return:
        apertures_: HB Aperture objects with new PHPP data. Pass along to any other HB component as usual.
"""

from itertools import izip
from honeybee.aperture import Aperture
import System

import LBT2PH
import LBT2PH.__versions__
import LBT2PH.windows
import LBT2PH.helpers
import LBT2PH.helpers_geometry

reload(LBT2PH)
reload(LBT2PH.__versions__)
reload(LBT2PH.windows)
reload(LBT2PH.helpers)
reload(LBT2PH.helpers_geometry)

ghenv.Component.Name = "LBT2PH PHPP Aperture"
LBT2PH.__versions__.set_component_params(ghenv, dev=False)
#-------------------------------------------------------------------------------

def aperture_sources():
    ''' Find the component input source node with the name "apertures" '''
    
    for input in ghenv.Component.Params.Input:
        if input.NickName == 'apertures':
            return input.Sources[0]
    
    return None

def window_rh_Guids():
    ''' Work backwards to get the Guid of the original input geom '''
    
    apertures_input_node = aperture_sources()
    if apertures_input_node is None:
        return None
    
    aperture_source_compo = apertures_input_node.Attributes.GetTopLevel.DocObject
    
    # Since the user MIGHT be using the normal Honeybee 'Aperture' OR they
    # might be using something like glazing by ratio, need to do some sort of check 
    # regarding where the aperture is coming from. Use the name? So for now, this
    # will only try and go get Rhino-scene info when used with the specific 
    # HB component? Might want to change that someday....
    
    rh_doc_window_guids = []
    if aperture_source_compo.Name != "HB Aperture":
        # if its not the 'HB Aperture' compo, just return about bunch of Nones....
        for input_aperture in apertures_input_node.VolatileData:
            rh_doc_window_guids.append( None )
        
        return rh_doc_window_guids
    
    for input in aperture_source_compo.Params.Input[0].VolatileData[0]:
        try:
            guid_as_str = input.ReferenceID.ToString() 
            rh_doc_window_guids.append( System.Guid(guid_as_str) )
        except:
            rh_doc_window_guids.append( None )
    
    return rh_doc_window_guids

def cleanInput(_inputList, targetListLength,):
    # Used to make sure the input lists are all the same length
    # if the input param list isn't the same, use only the first item for all
    
    output = []
    if len(_inputList) == targetListLength:
        for each in _inputList:
            output.append(each)
    elif len(_inputList) >= 1:
        for i in range(targetListLength):
            output.append(_inputList[0])
    elif len(_inputList) == 0:
        for i in range(targetListLength):
            output.append(None)
    
    return output


# Clean the GH component inputs
#-------------------------------------------------------------------------------
ud_frames = cleanInput(frames_, len(apertures))
ud_glazings = cleanInput(glazings_, len(apertures))
ud_installs = cleanInput([installs_], len(apertures))

install_depth = [LBT2PH.helpers.convert_value_to_metric(val, 'M') for val in  install_depth_]
ud_install_depths = cleanInput(install_depth, len(apertures))
gh_inputs = izip(ud_frames, ud_glazings,  ud_installs, ud_install_depths)


# Get the Rhino-Scene UserText (window Library)
# Build Glazing, Frame and Install objects for everything that is found there
#-------------------------------------------------------------------------------
if apertures:
    rh_doc_frame_and_glass_objs = LBT2PH.windows.build_frame_and_glass_objs_from_RH_doc(ghdoc, ghenv)


# Build the new Aperture and PHPP Window Objects
#-------------------------------------------------------------------------------
apertures_ = []
window_guids = []

if apertures:
    window_guids = window_rh_Guids()

for aperture, window_guid, gh_input in izip(apertures, window_guids, gh_inputs):
    # Get the Aperture from the Grasshopper scene
    # If its a generic dbl pane construction, that means no GH/HB user-determined input
    # so go try and find values from the Rhino scene instead
    if aperture.properties.energy.construction.display_name == 'Generic Double Pane':
        aperture_params = LBT2PH.helpers.get_rh_obj_UserText_dict(ghdoc, window_guid )
    else:
        aperture_params = {}
    
    #---------------------------------------------------------------------------
    # Unpack the Grasshopper-side UD Component values, deal with the installs
    ud_gh_frame, ud_gh_glazing, ud_gh_installs, ud_gh_install_depth = gh_input
    
    install_edges = ['InstallLeft', 'InstallRight', 'InstallBottom', 'InstallTop']
    if ud_gh_installs:
        for i, edge_name in enumerate(install_edges):
            try:
                aperture_params[edge_name] = ud_gh_installs[i]
            except IndexError as e:
                aperture_params[edge_name] = ud_gh_installs[0]
    
    # Build the right glazing/frame
    # 1) First build a standard glazing/frame from the HB Mat / Construction
    # 2) if any UD (Rhino or GH) side Objects, overide the obj with those instead
    
    glazing = LBT2PH.windows.PHPP_Glazing.from_HB_Const( aperture.properties.energy.construction )
    ud_rh_glazing = rh_doc_frame_and_glass_objs.get('lib_GlazingTypes', {}).get(aperture_params.get('GlazingType'))
    if ud_rh_glazing: glazing = ud_rh_glazing # Rhnino-side UD inputs
    if ud_gh_glazing: glazing = ud_gh_glazing # GH-side UD inputs
    
    frame = LBT2PH.windows.PHPP_Frame.from_HB_Const( aperture.properties.energy.construction )
    ud_rh_frame = rh_doc_frame_and_glass_objs.get('lib_FrameTypes', {}).get(aperture_params.get('FrameType'))
    if ud_rh_frame: frame = ud_rh_frame # Rhnino-side UD inputs
    if ud_gh_frame: frame = ud_gh_frame # GH-side UD inputs
    
    install = LBT2PH.windows.PHPP_Installs()
    install.install_L = aperture_params.get('InstallLeft', 1)
    install.install_R = aperture_params.get('InstallRight', 1)
    install.install_B = aperture_params.get('InstallBottom', 1)
    install.install_T = aperture_params.get('InstallTop', 1)
    
    install_depth = aperture_params.get('InstallDepth', 0.1)
    if ud_gh_install_depth:
        install_depth = ud_gh_install_depth
    
    #---------------------------------------------------------------------------
    # Create a new 'Window' Object based on the aperture, Frame, Glass, Installs
    # Create EP Constructions for each window (based on frame / glass)
    
    window_obj = LBT2PH.windows.PHPP_Window()
    
    window_obj.aperture = aperture
    window_obj.frame = frame
    window_obj.glazing = glazing
    window_obj.installs = install
    window_obj.install_depth = install_depth
    window_obj.variant_type = aperture_params.get('VariantType','a')
    
    window_EP_material = LBT2PH.windows.create_EP_window_mat( window_obj )
    window_EP_const = LBT2PH.windows.create_EP_const( window_EP_material )
    
    #---------------------------------------------------------------------------
    # Inset the Surface just a little bit to ensure it can be hosted properly
    inset_ap_geometry = LBT2PH.helpers_geometry.inset_LBT_Face3d(aperture.geometry, 0.0005)
    
    
    #---------------------------------------------------------------------------
    # Create a new Aperture object and modify it's properties
    # Package up the data onto the 'Aperture' objects' user_data
    
    new_ap = Aperture(aperture.identifier, inset_ap_geometry, is_operable=aperture.is_operable)
    
    new_ap.properties.energy.construction = window_EP_const
    new_name = aperture_params.get('Object Name', None)
    if new_name:
        new_ap.display_name = new_name
    
    new_ap = LBT2PH.helpers.add_to_HB_model( new_ap, 'phpp', window_obj.to_dict(), ghenv, 'overwrite' )
    
    apertures_.append(new_ap)