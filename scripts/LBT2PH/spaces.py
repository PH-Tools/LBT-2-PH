import rhinoscriptsyntax as rs
import random
import ghpythonlib.components as ghc
import Grasshopper.Kernel as ghK
import Rhino

from ladybug_geometry.geometry3d import Point3D
import LBT2PH
import LBT2PH.ventilation

reload(LBT2PH)
reload(LBT2PH.ventilation)

class TFA_Surface:
    ''' Represents an individual TFA Surface floor element '''
    
    def __init__(self, _surface, _host_room_name, _params, _sub_surfaces=[]):
        self._inset = 0.1
        self._neighbors = None
        self._area_gross = None

        self.id = random.randint(1000,9999)
        self.surface = _surface
        self.host_room_name = _host_room_name
        self.params = _params
        self.sub_surfaces = _sub_surfaces

    def __eq__(self, other):
        return self.id == other.id

    @property
    def neighbors(self):
        if self._neighbors is None:
            return set([self.id])
        else:
            return self._neighbors

    def get_vent_flow_rate(self, _type='V_sup'):
        ''' type = V_sup, V_eta or V_trans '''
        try:
            return float(self.params.get(_type, 0.0))
        except Exception as e:
            print(e)
            print('Error getting {} ventilation flow rate?'.format(_type))

    def set_vent_flow_rate(self, _type, _val):
        ''' type = V_sup, V_eta or V_trans '''
        try:
            self.params[_type] = float(_val)
        except Exception as e:
            print(e)
            print('Error setting {} ventilation flow rate to {}?'.format(_type, _val))

    @property
    def tfa_factor(self):
        try:
            return float(self.params.get('TFA_Factor', 1))
        except:
            print("Error getting the surface's TFA Factor?")
            return 1
    
    def set_tfa_factor(self, _val):
        try:
            self.params['TFA_Factor'] = float(_val)
        except Exception as e:
            print(e)

    @property
    def space_number(self):
        try:
            return str(self.params['Room_Number'])
        except:
            return None

    def set_space_number(self, _val):
        try:
            self.params['Room_Number'] = str(_val)
        except Exception as e:
            print(e)
    
    @property
    def space_name(self):
        return self.params.get('Object Name', None)

    def set_space_name(self, _val):
        try:
            self.params['Object Name'] = _val
        except Exception as e:
            print(e)
        
    @property
    def area_tfa(self):
        return self.area_gross * self.tfa_factor

    @property
    def area_gross(self):
        if self._area_gross:
            return self._area_gross
        else:
            return self.compute_area_gross()
    
    def set_area_gross(self, _val):
        try:
            self._area_gross = float(_val)
        except:
            print('Area Gross should be a number. Input {} is a {}'.format(_val, type(_val)))
    
    def compute_area_gross(self):
        try:
            return self.surface.GetArea()
        except:
            print('Error getting Gross Area of the TFA Surface?')
            return None
        
    @property
    def surface_perimeter(self):
        brep_edges = self.surface.Edges
        brep_edges = [edg.DuplicateCurve() for edg in brep_edges]
        srfc_perimeter = Rhino.Geometry.Curve.JoinCurves(brep_edges)

        return srfc_perimeter[0]

    def set_neighbors(self, _in):
        self._neighbors = self.neighbors.union(_in)

    @property
    def dict_key(self):
        if self.space_name and self.space_number:
            tfa_dict_key = '{}-{}'.format(self.space_number, self.space_name)
        else:
            tfa_dict_key = '{}-NONAME'.format(self.id)
        
        return tfa_dict_key

    def to_dict(self):
        d = {}

        d.update( {'id':self.id} )
        d.update( {'space_number':self.space_number} )
        d.update( {'space_name':self.space_name} )
        d.update( {'host_room_name':self.host_room_name} )
        d.update( {'params':self.params} )
        d.update( {'area_gross':self.area_gross})

        return d

    @classmethod
    def from_dict(cls, _dict_tfa, _dict_sub_surfaces):
        
        surface = None
        host_room_name = _dict_tfa['host_room_name']
        params = _dict_tfa['params']
        sub_surfaces = []
        for sub_surface in _dict_sub_surfaces.values():
            new_sub_surface = cls.from_dict( sub_surface, {} )
            sub_surfaces.append( new_sub_surface )

        new_tfa_obj = cls(surface, host_room_name, params, sub_surfaces)
        new_tfa_obj.id = _dict_tfa['id']        
        new_tfa_obj._inset = 0.1
        new_tfa_obj._neighbors = None
        new_tfa_obj._area_gross = _dict_tfa['area_gross'] 

        return new_tfa_obj

    def __unicode__(self):
        return u'A PHPP Treated Floor Area (TFA) Object: < {} >'.format(self.id)
    def __str__(self):
        return unicode(self).encode('utf-8')
    def __repr__(self):
       return "{}(_surface={!r}, _host_room_name={!r}, "\
               "params={!r}, _sub_surfaces={!r} )".format(
               self.__class__.__name__,
               self.surface,
               self.host_room_name,
               self.params,
               self.sub_surfaces)


class Volume:
    ''' Represents an individual volume / part of a larger Space '''

    def __init__(self, _tfa_surface=None, _space_geometry=None, _space_height=2.5):
        self.id = random.randint(1000,9999)
        self.tfa_surface = _tfa_surface
        self._space_geom = _space_geometry
        self._space_height = _space_height
        self._space_vn50 = None
        self._offset_z = 0
        self._phpp_vent_flow_rates = {'V_sup':0, 'V_eta':0, 'V_trans':0}

    @property
    def dict_key(self):
        return '{}-{}'.format(self.volume_number, self.volume_name)
    
    @property
    def host_room_name(self):
        return self.tfa_surface.host_room_name

    @property
    def volume_name(self):
        return self.tfa_surface.space_name
    
    @property
    def volume_number(self):
        return self.tfa_surface.space_number

    @property
    def volume_height(self):
        try:
            # Try and get the height from the input geometry
            z_positions = []
            vol_brep = self.volume_brep
            for brep in vol_brep:
                vert_list = brep.Vertices
                for vert in vert_list.Item:
                    z_positions.append( vert.Location.Z )

            highest =  max(z_positions)
            lowest = min(z_positions)
            vertical_distance = abs(highest - lowest)
            
            return float( vertical_distance )
        except:
            try:
                return float(self._space_height)
            except:
                return 2.5

    @property
    def volume_brep(self):
        try:
            if self._space_geom:
                return self._build_volume_brep_from_geom()
            else:
                return self._build_volume_brep_from_zone()
        except Exception as e:
            return None

    def _build_volume_brep_from_geom(self):
        results = ghc.BrepJoin( [self.tfa_surface.surface, self._space_geom.breps] )
        #Un-pack the results
        output = []
        if results:
            for brep, closed in zip(results.breps, results.closed):
                if closed:
                    output.append( brep )

        return output  

    def _build_volume_brep_from_zone(self):      
        # Floor Surface
        floor_surface = rs.coercebrep(self.tfa_surface.surface)
        floor_surface = ghc.Move(floor_surface, ghc.UnitZ(self._offset_z) )[0]  # 0 is the new translated geometry

        # Extrusion curve
        surface_centroid = Rhino.Geometry.AreaMassProperties.Compute(floor_surface).Centroid
        end_point = ghc.ConstructPoint(surface_centroid.X, surface_centroid.Y, surface_centroid.Z + self._space_height)
        extrusion_curve = rs.AddLine(surface_centroid, end_point)

        volume_brep = rs.ExtrudeSurface(surface=floor_surface, curve=extrusion_curve, cap=True)
        volume_brep = rs.coercebrep(volume_brep)
        
        return [volume_brep]

    def _get_vent_flow_rate(self, _type):
        try:
            return float(self.tfa_surface.get_vent_flow_rate(_type))
        except:
            return self._phpp_vent_flow_rates[_type]

    def set_phpp_vent_rates(self, _dict):
        self._phpp_vent_flow_rates = _dict
        
        self.tfa_surface.set_vent_flow_rate('V_sup', _dict['V_sup'])
        self.tfa_surface.set_vent_flow_rate('V_eta', _dict['V_eta'])
        self.tfa_surface.set_vent_flow_rate('V_trans', _dict['V_trans'])

    @property
    def area_tfa(self):
        return float( self.tfa_surface.area_tfa )

    @property
    def vn50(self):
        try:
            volumes = []
            breps = self.volume_brep
            for brep in breps:
                try:
                    volumes.append( abs(float( brep.GetVolume() ) ) )
                except:
                    volumes.append( 0 )
            
            return sum(volumes)
        except Exception as e:
            try:
                return float(self._space_vn50)
            except:
                return 5

    def to_dict(self):
        d = {}
        d.update( {'id': self.id} )
        d.update( {'volume_height': self.volume_height})
        d.update( {'tfa_surface': self.tfa_surface.to_dict() } )
        d.update( {'_space_vn50': self.vn50 } )

        tfa_sub_surfaces = {}
        for sub_surface in self.tfa_surface.sub_surfaces:
            key = '{}_{}'.format(sub_surface.dict_key, str(sub_surface.id) )
            tfa_sub_surfaces.update( { key:sub_surface.to_dict() } )
        d.update( {'tfa_sub_surfaces': tfa_sub_surfaces } )
    
        vent_rates = {}
        vent_rates.update( {'V_sup':self._get_vent_flow_rate('V_sup') })
        vent_rates.update( {'V_eta':self._get_vent_flow_rate('V_eta') })
        vent_rates.update( {'V_trans':self._get_vent_flow_rate('V_trans') })
        d.update( {'_phpp_vent_flow_rates':vent_rates} )

        return d

    @classmethod
    def from_dict(cls, _dict):
        
        new_volume = cls()
        new_volume.tfa_surface = TFA_Surface.from_dict( _dict['tfa_surface'], _dict['tfa_sub_surfaces'] )
        new_volume._space_geom = None
        new_volume.volume_height = _dict['volume_height']
        new_volume.id = _dict['id']
        new_volume._space_vn50 = _dict['_space_vn50']
        new_volume._phpp_vent_flow_rates = _dict['_phpp_vent_flow_rates']
    
        return new_volume

    def __unicode__(self):
        return u'A PHPP Space Volume Object: < {} >'.format(self.id)
    def __str__(self):
        return unicode(self).encode('utf-8')
    def __repr__(self):
       return "{}(_tfa_surface={!r}, _space_geometry={!r}, "\
               "_space_height={!r})".format(
               self.__class__.__name__,
               self.tfa_surface,
               self._space_geom,
               self._space_height)


class Space:
    ''' A 'Space' or Room in a Zone. Made up of one or more Volumes/parts '''
    
    def __init__(self, _volumes=None, _vent_sched=LBT2PH.ventilation.PHPP_Sys_VentSchedule() ):
        self.id = random.randint(1000,9999)
        self.volumes = _volumes
        self.phpp_vent_system_id = 'default'
        self._phpp_vent_flow_rates = {'V_sup':0, 'V_eta':0, 'V_trans':0}
        self.vent_sched = _vent_sched
    
    @property
    def space_vent_supply_air(self):
        vent_rates = []
        try:
            for vol in self.volumes:
                vent_rates.append( vol._get_vent_flow_rate('V_sup') )
            return max(vent_rates)
        except:
            return self._phpp_vent_flow_rates['V_sup']
        
    @property
    def space_vent_extract_air(self):
        vent_rates = []
        try:
            for vol in self.volumes:
                vent_rates.append( vol._get_vent_flow_rate('V_eta') )           
            return max(vent_rates)
        except:
            return self._phpp_vent_flow_rates['V_eta']
        
    @property
    def space_vent_transfer_air(self):
        vent_rates = []
        try:
            for vol in self.volumes:
                vent_rates.append( vol._get_vent_flow_rate('V_trans') )
            return max(vent_rates)
        except:
            return self._phpp_vent_flow_rates['V_trans']

    @property
    def space_breps(self):
        output = []
        for volume in self.volumes:
            volume_brep = volume.volume_brep
        
        
            if volume_brep is None:
                continue

            if isinstance(volume.volume_brep, list):
                for brep in volume.volume_brep:
                    output.append(brep)
            else:
                output = volume.volume_brep

        return output
        
    @property
    def host_room_name(self):
        host_room_names = set()
        for volume in self.volumes:
            host_room_names.add(volume.host_room_name)

        if len(host_room_names) != 1:
            print('Error. Multiple Host Zones found? Fix your room geometry')
            return host_room_names.pop()
        else:
            return host_room_names.pop()

    @property
    def space_name(self):
        space_names = set()
        for volume in self.volumes:
            space_names.add(volume.volume_name)
        
        if len(space_names) != 1:
            print('Error. Multiple volume names found? Fix your room parameters')
            return None
        else:
            return space_names.pop()

    @property
    def space_number(self):
        space_nums= set()
        for volume in self.volumes:
            space_nums.add(volume.volume_number)
        
        if len(space_nums) != 1:
            print('Error. Multiple volume numbers found? Fix your room parameters')
            return None
        else:
            return str(space_nums.pop())

    @property
    def dict_key(self):
        return '{}-{}'.format(self.space_number, self.space_name)

    @property
    def space_vn50(self):
        return sum([volume.vn50 for volume in self.volumes])

    @property
    def space_tfa(self):
        return sum([volume.area_tfa for volume in self.volumes])

    @property
    def space_avg_clear_ceiling_height(self):
        return sum([volume.volume_height for volume in self.volumes])/len(self.volumes)

    def set_phpp_vent_rates(self, _dict):
        if 'V_sup' in _dict.keys() and 'V_eta' in _dict.keys() and 'V_trans' in _dict.keys():
            self._phpp_vent_flow_rates = _dict

        for vol in self.volumes:
            vol.set_phpp_vent_rates( _dict )

    def to_dict(self):
        d = {}
        d.update( {'id': self.id} )
        d.update( {'phpp_vent_system_id': self.phpp_vent_system_id} )
        d.update( {'volumes' : {} } )

        for volume in self.volumes:
            key = '{}_{}'.format(volume.dict_key, volume.id)
            d['volumes'].update( { key : volume.to_dict() } )
        
        vent_rates = {}
        vent_rates.update( {'V_sup': self.space_vent_supply_air} )
        vent_rates.update( {'V_eta': self.space_vent_extract_air} )
        vent_rates.update( {'V_trans': self.space_vent_transfer_air} )
        d.update( {'_phpp_vent_flow_rates': vent_rates} )
        d.update( {'vent_sched': self.vent_sched.to_dict()} )

        return d

    @classmethod
    def from_dict(cls, _dict):

        dict_volumes = _dict['volumes']
        volumes = []
        for volume in dict_volumes.values():
            new_volume = Volume.from_dict(volume)
            volumes.append(new_volume)

        new_space =  cls()
        new_space.id = _dict['id']
        new_space.phpp_vent_system_id = _dict['phpp_vent_system_id']
        new_space._phpp_vent_flow_rates = _dict['_phpp_vent_flow_rates']
        new_space.volumes = volumes
        new_space.vent_sched = LBT2PH.ventilation.PHPP_Sys_VentSchedule.from_dict( _dict['vent_sched'] )

        return new_space

    def __unicode__(self):
        return u'A PHPP Space Object: < {} >'.format(self.id)
    def __str__(self):
        return unicode(self).encode('utf-8')
    def __repr__(self):
       return "{}(_volumes={!r} )".format(
               self.__class__.__name__,
               self.volumes)


def find_tfa_host_room(_tfa_srfc_geom, _hb_rooms):
    srfc_centroid = Rhino.Geometry.AreaMassProperties.Compute(_tfa_srfc_geom).Centroid
    srfc_centroid = Point3D(srfc_centroid.X, srfc_centroid.Y, srfc_centroid.Z)
    
    host_room = None
    for room in _hb_rooms:
        if room.geometry.is_point_inside( srfc_centroid ):
            host_room = room.display_name
            break

    return host_room

def get_hb_room_floor_surfaces(_room):
    hb_floor_surfaces = []
    for face in _room.faces:
        if str(face.type) == 'Floor':
            hb_floor_surfaces.append(face)

    return hb_floor_surfaces

def get_tfa_surface_data_from_Rhino(_guid):  
    geom = rs.coercebrep(_guid)
    nm = rs.ObjectName(_guid)
    
    params = {}
    param_keys = rs.GetUserText(_guid)
    for k in param_keys:
        params[k] =rs.GetUserText(_guid, k)
    
    if 'Object Name' in params.keys():
        params['Object Name'] = nm

    return (geom, nm, params)

def find_neighbors(_dict_of_TFA_objs):
    for tfa_a in _dict_of_TFA_objs.values():
        for tfa_b in _dict_of_TFA_objs.values():
            if ghc.BrepXBrep(tfa_a.surface, tfa_b.surface).curves:
                tfa_a.set_neighbors(tfa_b.neighbors)
                tfa_b.set_neighbors(tfa_a.neighbors)

    return None

def bin_tfa_srfcs_by_neighbor(_tfa_srfc_objs):
    srfcSets = {}
    for room_name, room in _tfa_srfc_objs.items():
        for k2, v2 in room.items():
            if len(v2.neighbors) == 1:
                srfcSets[v2.id] = [v2]
            else:
                for id_num in v2.neighbors:
                    if id_num in srfcSets.keys():
                        srfcSets[id_num].append(v2)
                        break
                else:
                    srfcSets[v2.id] = [v2]
    
    return srfcSets

def join_touching_tfa_groups(_tfa_surface_groups):
    tfa_srfcs_joined = []
    
    for group in _tfa_surface_groups.values():
        # if there is only a single element in the group, add it to the list
        # otherwise, try and join together the elements in the group
        
        if len(group) == 1:
            tfa_srfcs_joined.append(group[0])
        else:
            ventFlowRates_Sup = []
            ventFlowRates_Eta = []
            ventFlowRates_Tran = []
            areas_tfa = []
            areas_gross = []
            srfc_exterior_perimeters = []
            sub_surfaces = []
            for tfa_srfc in group:
                # Get the ventilation flow rates
                ventFlowRates_Sup.append( tfa_srfc.get_vent_flow_rate('V_sup') )
                ventFlowRates_Eta.append( tfa_srfc.get_vent_flow_rate('V_eta') )
                ventFlowRates_Tran.append( tfa_srfc.get_vent_flow_rate('V_trans') )

                # Get the geometric information
                areas_tfa.append(tfa_srfc.area_tfa)
                areas_gross.append(tfa_srfc.compute_area_gross())
                srfc_exterior_perimeters.append(tfa_srfc.surface_perimeter)
                sub_surfaces.append(tfa_srfc)

            # Build the new TFA surface
            perim_curve = ghc.RegionUnion(srfc_exterior_perimeters)
            unioned_surface = Rhino.Geometry.Brep.CreatePlanarBreps(perim_curve, 0.01)
            if len(unioned_surface) != 0:
                unioned_surface = unioned_surface[0]
            else:
                break

            host_room_name = group[0].host_room_name
            params = group[0].params
            unionedTFAObj = TFA_Surface(unioned_surface, host_room_name, params, sub_surfaces)

            # Set the new TFA Surface's param properties
            unionedTFAObj.set_area_gross( sum(areas_gross) )
            unionedTFAObj.set_tfa_factor( sum(areas_tfa) / sum(areas_gross) )
            unionedTFAObj.set_space_number( group[0].space_number )
            unionedTFAObj.set_space_name( group[0].space_name )
            unionedTFAObj.set_vent_flow_rate('V_sup', max(ventFlowRates_Sup) )
            unionedTFAObj.set_vent_flow_rate('V_eta', max(ventFlowRates_Eta) )
            unionedTFAObj.set_vent_flow_rate('V_trans', max(ventFlowRates_Tran) )

            #
            #
            #
            #
            # TODO: Join all the 'Non-Res' stuff together
            #
            # 
            # 
            # 
            # 

            tfa_srfcs_joined.append(unionedTFAObj)
    
    return tfa_srfcs_joined

def display_host_error(_tfa_obj, _ghenv):
    try:
        tfa_id = _tfa_obj.get_dict_key()
        msg = "Couldn't figure out which room/zone the tfa surface '{}' should "\
        "go in?\nMake sure the room is completely inside one or another zone.".format(tfa_id)
        _ghenv.Component.AddRuntimeMessage(ghK.GH_RuntimeMessageLevel.Warning, msg)

    except:
        msg = "Couldn't figure out which room/zone the tfa surface 'Un-Named' should "\
        "go in?\nMake sure to set the params for each surface and that they are inside "\
        "\none or another zone"
        _ghenv.Component.AddRuntimeMessage(ghK.GH_RuntimeMessageLevel.Warning, msg)

    return None