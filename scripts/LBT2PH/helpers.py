from contextlib import contextmanager
from copy import deepcopy
import scriptcontext as sc
import Rhino
from copy import deepcopy
import re
import Grasshopper.Kernel as ghK

import spaces
import occupancy
reload( spaces )
reload( occupancy )

from honeybee.typing import clean_and_id_ep_string
from honeybee_energy.schedule.ruleset import ScheduleRuleset
from honeybee_energy.lib.scheduletypelimits import schedule_type_limit_by_identifier


def add_to_HB_model( _hb_model, _key, _dict, _ghenv, _write='update' ):

    user_data = deepcopy( _hb_model.user_data )
    if not user_data:
        if _key == 'phpp':
            _hb_model.user_data = {'phpp': _dict }
            return _hb_model
        else:
            _hb_model.user_data = {'phpp': { _key: _dict} }
            return _hb_model
    
    try:
        if _write == 'update':
            user_data['phpp'][_key].update( _dict )
        elif _write == 'overwrite':
            user_data['phpp'][_key] = _dict
    except KeyError as e:
        try:
            user_data['phpp'].update( {_key:_dict } )
        except KeyError:
            try:
                user_data = {'phpp':{_key:_dict }}
            except Exception as e:
                msg = e
                msg += 'Error writing data to the model user_data?'
                _ghenv.Component.AddRuntimeMessage( ghK.GH_RuntimeMessageLevel.Error, msg )

    _hb_model.user_data = user_data
    return _hb_model



#
#
#
# Remove?
def add_to_hb_obj_user_data(_hb_obj, key, _val):
    if _hb_obj.user_data is None:
        _hb_obj.user_data = {}
    
    if not isinstance(_hb_obj.user_data, dict):
        raise Exception
    
    # Decided to do a deepcopy here, otherwise ref pointer always
    # goes to the same dict which makes it confusing as things are added/edited.
    # I dont *think* it would error without the copy? But more predictable with it.
    new_user_data = deepcopy(_hb_obj.user_data)
    if new_user_data.has_key('phpp'):
        if new_user_data['phpp'].has_key(key):
            new_user_data['phpp'][key].update(_val)
        else:
            new_user_data['phpp'][key] = _val
    else:
        new_user_data['phpp'] = {}
        new_user_data['phpp'][key] = _val
    
    _hb_obj.user_data = new_user_data
    
    return _hb_obj
#
#
#
#

@contextmanager
def context_rh_doc(_ghdoc):
    ''' Switches the sc.doc to the Rhino Active Doc temporaily '''
    if not _ghdoc:
        return

    try:
        sc.doc = Rhino.RhinoDoc.ActiveDoc
        yield
    finally:
        sc.doc = _ghdoc

def preview_obj(_classObj):
    ''' For looking at the contents of a Class Object '''

    if not hasattr(_classObj, '__dict__'):
    	print('{} object "{}" has no "__dict__" attribute.'.format(type(_classObj), _classObj))
    	return None
    
    print('-------')
    for item_key, item in _classObj.__dict__.items():
        print(item_key, "::", item)
        try:
            for k, v in item.__dict__.items():
                print("   > {} :: {}".format(k, v))
        except:
            pass

def find_input_string(_in):
    """ Util func  used by the unit converter """
    
    evalString = str(_in).upper()
    
    if 'FT' in evalString or "'" in evalString:
        inputUnit = 'FT'
    elif 'IN' in evalString or '"' in evalString:
        inputUnit = 'IN'
    elif 'MM' in evalString:
        inputUnit = 'MM'
    elif 'CM' in evalString:
        inputUnit = 'CM'
    elif 'M' in evalString and 'MM' not in evalString:
        inputUnit = 'M'
    elif 'IP' in evalString:
        inputUnit = 'IP'
    elif 'FT3' in evalString:
        inputUnit = 'FT3'
    else:
        inputUnit = 'SI'
    
    return inputUnit

def convert_value_to_metric(_inputString, _outputUnit):
    """ Will convert a string such as "12 FT" into the corresponding Metric unit
    
    Arguments:
        _inputString: String: The input value from the user
        _outputUnit: String: ('M', 'CM', 'MM', 'W/M2K', 'W/MK', 'M3') The desired unit
    """
    schema = {
                'M':{'SI': 1, 'M':1, 'CM':0.01, 'MM':0.001, 'FT':0.3048, "'":0.3048, 'IN':0.0254, '"':0.0254},
                'CM':{'SI': 1, 'M':100, 'CM':1, 'MM':0.1, 'FT':30.48, "'":30.48, 'IN':2.54, '"':2.54},
                'MM':{'SI': 1, 'M':1000, 'CM':10, 'MM':1, 'FT':304.8, "'":304.8, 'IN':25.4, '"':25.4},
                'W/M2K':{'SI':1, 'IP':5.678264134}, # IP=Btu/hr-sf-F
                'W/MK':{'SI':1, 'IP':1.730734908}, #IP=Btu/hr-ft-F
                'M3':{'SI':1, 'FT3':0.028316847},
              }
    
    inputValue = _inputString
    
    if _inputString is None:
        return None
    
    try:
        return float(inputValue)
    except:
        try:
            # Pull out just the decimal numeric characters, if any
            for each in re.split(r'[^\d\.]', _inputString):
                if len(each)>0:
                    inputValue = each
                    break # so it will only take the first number found, "123 ft3" doesn't work otherwise
            
            inputUnit = find_input_string(_inputString)
            conversionFactor = schema.get(_outputUnit, {}).get(inputUnit, 1)
            return float(inputValue) * float(conversionFactor)
        except:
            return inputValue

def create_hb_constant_schedule(_name, _type_limit='Fractional'):
    type_limit = schedule_type_limit_by_identifier( _type_limit )

    schedule = ScheduleRuleset.from_constant_value(
        clean_and_id_ep_string(_name), 1, type_limit)

    schedule.display_name = _name

    return schedule

def get_model_tfa(_model):
    tfa = 0
    for room in _model.rooms:
        for space in room.user_data.get('phpp', {}).get('spaces').values():
            space_obj = spaces.Space.from_dict( space )
            tfa += space_obj.space_tfa
    
    return tfa
 
def get_model_occupancy(_model, _ghenv):
    try:
        occ_dict = _model.user_data.get('phpp', {}).get('occupancy', None)
        
        if not occ_dict:
            raise ValueError
        
        occ_obj = occupancy.Occupancy.from_dict( occ_dict )
        
        return occ_obj
    except ValueError:
        msg = "Error getting Occupancy from the Honeybee Model? Please use an LBT2PH 'Occupancy'\n"\
        "component before using this one in order to set the number of units and the occupancy level of the\n"\
        "building. For now, I will assume 1-Unit and calculate the occupancy based on the model's gross floor area"
        _ghenv.Component.AddRuntimeMessage( ghK.GH_RuntimeMessageLevel.Warning, msg  )
        
        occ_obj = occupancy.Occupancy( _tfa=_model.floor_area  )
        return occ_obj

