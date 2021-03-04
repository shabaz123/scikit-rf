

'''
.. module:: skrf.networkSet

========================================
networkSet (:mod:`skrf.networkSet`)
========================================

Provides a class representing an un-ordered set of n-port microwave networks.


Frequently one needs to make calculations, such as mean or standard
deviation, on an entire set of n-port networks. To facilitate these
calculations the :class:`NetworkSet` class provides convenient
ways to make such calculations.

Another usage is to interpolate a set of Networks which depend of
an parameter (like a knob, or a geometrical parameter).

The results are returned in :class:`~skrf.network.Network` objects, so they can be plotted and saved in the same way one would do with a
:class:`~skrf.network.Network`.

The functionality in this module is provided as methods and
properties of the :class:`NetworkSet` Class.


NetworkSet Class
================

.. autosummary::
   :toctree: generated/

   NetworkSet

NetworkSet Utilities
====================

.. autosummary::
   :toctree: generated/

   func_on_networks
   getset


'''

import os
from . network import average as network_average
from . network import Network, PRIMARY_PROPERTIES, COMPONENT_FUNC_DICT, Y_LABEL_DICT

from . import mathFunctions as mf
import zipfile
from copy import deepcopy
import warnings
import numpy as npy
from scipy.interpolate import interp1d
# import matplotlib.pyplot as plb
from . util import now_string_2_dt
# delayed imports due to circular dependencies
# NetworkSet.from_dir : from io.general import read_all_networks

class NetworkSet(object):
    '''
    A set of Networks.

    This class allows functions on sets of Networks, such as mean or
    standard deviation, to be calculated conveniently. The results are
    returned in :class:`~skrf.network.Network` objects, so that they may be
    plotted and saved in like :class:`~skrf.network.Network` objects.

    This class also provides methods which can be used to plot uncertainty
    bounds for a set of :class:`~skrf.network.Network`.

    The names of the :class:`NetworkSet` properties are generated
    dynamically upon initialization, and thus documentation for
    individual properties and methods is not available. However, the
    properties do follow the convention::

            >>> my_network_set.function_name_network_property_name

    For example, the complex average (mean)
    :class:`~skrf.network.Network` for a
    :class:`NetworkSet` is::

            >>> my_network_set.mean_s

    This accesses the property 's', for each element in the
    set, and **then** calculates the 'mean' of the resultant set. The
    order of operations is important.

    Results are returned as :class:`~skrf.network.Network` objects,
    so they may be plotted or saved in the same way as for
    :class:`~skrf.network.Network` objects::

            >>> my_network_set.mean_s.plot_s_mag()
            >>> my_network_set.mean_s.write_touchstone('mean_response')

    If you are calculating functions that return scalar variables, then
    the result is accessible through the Network property .s_re. For
    example::

            >>> std_s_deg = my_network_set.std_s_deg

    This result would be plotted by::

            >>> std_s_deg.plot_s_re()


    The operators, properties, and methods of NetworkSet object are
    dynamically generated by private methods

     * :func:`~NetworkSet.__add_a_operator`
     * :func:`~NetworkSet.__add_a_func_on_property`
     * :func:`~NetworkSet.__add_a_element_wise_method`
     * :func:`~NetworkSet.__add_a_plot_uncertainty`

    thus, documentation on the individual methods and properties are
    not available.


    '''

    def __init__(self, ntwk_set, name = None):
        '''
        Initializer for NetworkSet

        Parameters
        -----------
        ntwk_set : list of :class:`~skrf.network.Network` objects
                the set of :class:`~skrf.network.Network` objects
        name : string
                the name of the NetworkSet, given to the Networks returned
                from properties of this class.
        '''
        ## type checking
        if hasattr(ntwk_set, 'values'):
            ntwk_set = list(ntwk_set.values())

        # did they pass a list of Networks?
        if not isinstance(ntwk_set[0], Network):
            raise(TypeError('input must be list of Network types'))

        # do all Networks have the same # ports?
        if len (set([ntwk.number_of_ports for ntwk in ntwk_set])) >1:
            raise(ValueError('All elements in list of Networks must have same number of ports'))

        # is all frequency information the same?
        if npy.all([(ntwk_set[0].frequency == ntwk.frequency) \
                for ntwk in ntwk_set]) == False:
            raise(ValueError('All elements in list of Networks must have same frequency information'))

        ## initialization
        # we are good to go
        self.ntwk_set = ntwk_set
        self.name = name

        # create list of network properties, which we use to dynamically
        # create a statistical properties of this set
        network_property_list = [k+'_'+l \
            for k in PRIMARY_PROPERTIES \
            for l in COMPONENT_FUNC_DICT.keys()] + \
            ['passivity','s']

        # dynamically generate properties. this is slick.
        max, min = npy.max, npy.min
        max.__name__ = 'max'
        min.__name__ = 'min'
        for network_property_name in network_property_list:
            for func in [npy.mean, npy.std, max, min]:
                self.__add_a_func_on_property(func, network_property_name)

            if 'db' not in network_property_name:# != 's_db' and network_property_name != 's':
                # db uncertainty requires a special function call see
                # plot_uncertainty_bounds_s_db
                self.__add_a_plot_uncertainty(network_property_name)
                self.__add_a_plot_minmax(network_property_name)

            self.__add_a_element_wise_method('plot_'+network_property_name)
            self.__add_a_element_wise_method('plot_s_db')
            self.__add_a_element_wise_method('plot_s_db_time')
        for network_method_name in \
                ['write_touchstone','interpolate','plot_s_smith']:
            self.__add_a_element_wise_method(network_method_name)

        for operator_name in \
                ['__pow__','__floordiv__','__mul__','__div__','__add__','__sub__']:
            self.__add_a_operator(operator_name)

    @classmethod
    def from_zip(cls, zip_file_name, sort_filenames=True, *args, **kwargs):
        '''
        creates a NetworkSet from a zipfile of touchstones.

        Parameters
        -----------
        zip_file_name : string
            name of zipfile
        sort_filenames: Boolean
            sort the filenames in the zip file before constructing the
            NetworkSet
        \\*args,\\*\\*kwargs : arguments
            passed to NetworkSet constructor

        Examples
        ----------

        >>> import skrf as rf
        >>> my_set = rf.NetworkSet.from_zip('myzip.zip')

        '''
        z = zipfile.ZipFile(zip_file_name)
        filename_list = z.namelist()

        ntwk_list = []

        if sort_filenames:
            filename_list.sort()


        for filename in filename_list:
            # try/except block in case not all files are touchstones
            n= Network()
            try:
                n.read_touchstone(z.open(filename))
                ntwk_list.append(n)
                continue
            except:
                pass
            try:
                n.read(z.open(filename))
                ntwk_list.append(n)
                continue
            except:
                pass

        return cls(ntwk_list)

    @classmethod
    def from_dir(cls, dir='.',*args, **kwargs):
        '''
        Create a NetworkSet from a directory containing Networks

        This just calls ::

            rf.NetworkSet(rf.read_all_networks(dir), *args, **kwargs)

        Parameters
        ---------------
        dir : str
            directory containing Network files.

        \*args, \*\*kwargs :
            passed to NetworkSet constructor

        Examples
        ----------

        >>> my_set = rf.NetworkSet.from_dir('./data/')
        '''
        from . io.general import read_all_networks
        return cls(read_all_networks(dir), *args, **kwargs)



    @classmethod
    def from_s_dict(cls,d, frequency, *args, **kwargs):
        '''
        Create a NetworkSet from a dictionary of s-parameters

        The resultant elements of the NetworkSet are named by the keys of
        the dictionary.

        Parameters
        -------------
        d : dict
            dictionary of s-parameters data. values of this should be
            :class:`numpy.ndarray` assignable to :attr:`skrf.network.Network.s`
        frequency: :class:`~skrf.frequency.Frequency` object
            frequency assigned to each network

        \*args, \*\*kwargs :
            passed to Network.__init__ for each key/value pair of d

        Returns
        ----------
        ns : NetworkSet

        See Also
        ----------
        NetworkSet.to_s_dict
        '''
        return cls([Network(s=d[k], frequency=frequency, name=k,
                            *args, **kwargs)  for k in d])




    def __add_a_operator(self,operator_name):
        '''
        adds a operator method to the NetworkSet.

        this is made to
        take either a Network or a NetworkSet. if a Network is passed
        to the operator, each element of the set will operate on the
        Network. If a NetworkSet is passed to the operator, and is the
        same length as self. then it will operate element-to-element
        like a dot-product.
        '''
        def operator_func(self, other):
            if isinstance(other, NetworkSet):
                if len(other) != len(self):
                    raise(ValueError('Network sets must be of same length to be cascaded'))
                return NetworkSet([self.ntwk_set[k].__getattribute__(operator_name)(other.ntwk_set[k]) for k in range(len(self))])

            elif isinstance(other, Network):
                return NetworkSet([ntwk.__getattribute__(operator_name)(other) for ntwk in self.ntwk_set])

            else:
                raise(TypeError('NetworkSet operators operate on either Network, or NetworkSet types'))
        setattr(self.__class__,operator_name,operator_func)


    def __str__(self):
        '''
        '''

        return self.ntwk_set.__str__()

    def __repr__(self):
        return self.__str__()

    def __getitem__(self,key):
        '''
        returns an element of the network set
        '''
        if isinstance(key, str):
            # if they pass a string then slice each network in this set
            return NetworkSet([k[key] for k in self.ntwk_set],
                              name = self.name)
        else:
            return self.ntwk_set[key]

    def __len__(self):
        '''
        returns an element of the network set
        '''
        return len(self.ntwk_set)


    def __add_a_element_wise_method(self,network_method_name):
        def func(self,  *args, **kwargs):
            return self.element_wise_method(network_method_name, *args, **kwargs)
        setattr(self.__class__,network_method_name,func)


    def __add_a_func_on_property(self,func,network_property_name):
        '''
        dynamically adds a property to this class (NetworkSet).
        this is mostly used internally to genrate all of the classes
        properties.

        takes:
                network_property_name: a property of the Network class,
                        a string. this must have a matrix output of shape fxnxn
                func: a function to be applied to the network_property
                        accross the first axis of the property's output



        example:
                my_ntwk_set.add_a_func_on_property('s',mean)


        '''
        fget = lambda self: fon(self.ntwk_set,func,network_property_name,\
                name = self.name)
        setattr(self.__class__,func.__name__+'_'+network_property_name,\
                property(fget))

    def __add_a_plot_uncertainty(self,network_property_name):
        '''

        takes:
                network_property_name: a property of the Network class,
                        a string. this must have a matrix output of shape fxnxn



        example:
                my_ntwk_set.add_a_func_on_property('s',mean)


        '''
        def plot_func(self,*args, **kwargs):
            kwargs.update({'attribute':network_property_name})
            self.plot_uncertainty_bounds_component(*args,**kwargs)

        setattr(self.__class__,'plot_uncertainty_bounds_'+\
                network_property_name,plot_func)

        setattr(self.__class__,'plot_ub_'+\
                network_property_name,plot_func)

    def __add_a_plot_minmax(self,network_property_name):
        '''

        takes:
                network_property_name: a property of the Network class,
                        a string. this must have a matrix output of shape fxnxn



        example:
                my_ntwk_set.add_a_func_on_property('s',mean)


        '''
        def plot_func(self,*args, **kwargs):
            kwargs.update({'attribute':network_property_name})
            self.plot_minmax_bounds_component(*args,**kwargs)

        setattr(self.__class__,'plot_minmax_bounds_'+\
                network_property_name,plot_func)

        setattr(self.__class__,'plot_mm_'+\
                network_property_name,plot_func)

    def to_dict(self):
        """
        Returns a dictionary representation of the NetworkSet

        The returned dictionary has the Network names for keys, and the
        Networks as values.
        """
        return dict([(k.name, k) for k in self.ntwk_set])

    def to_s_dict(ns, *args, **kwargs):
        """
        Converts a NetworkSet to a dictionary of s-parameters

        The resultant  keys of the dictionary are the names of the Networks
        in NetworkSet

        Parameters
        -------------
        ns : NetworkSet
            dictionary of s-parameters data. values of this should be
            :class:`numpy.ndarray` assignable to :attr:`skrf.network.Network.s`
        frequency: :class:`~skrf.frequency.Frequency` object
            frequency assigned to each network

        \*args, \*\*kwargs :
            passed to Network.__init__ for each key/value pair of d

        Returns
        ----------
        s_dict : dictionary
            contains s-parameters in the form of complex numpy arrays

        See Also
        --------
        NetworkSet.from_s_dict
        """
        d = ns.to_dict()
        for k in d:
            d[k] = d[k].s
        return d



    def element_wise_method(self,network_method_name, *args, **kwargs):
        '''
        calls a given method of each element and returns the result as
        a new NetworkSet if the output is a Network.
        '''
        output = [ntwk.__getattribute__(network_method_name)(*args, **kwargs) for ntwk in self.ntwk_set]
        if isinstance(output[0],Network):
            return NetworkSet(output)
        else:
            return output

    def copy(self):
        '''
        copies each network of the network set.
        '''
        return NetworkSet([k.copy() for k in self.ntwk_set])

    def sort(self, key=lambda x: x.name, **kwargs):
        '''
        sort this network set.

        Parameters
        -------------
        **kwargs : dict
            keyword args passed to builtin sorted acting on self.ntwk_set

        Examples
        -----------
        >>> ns = rf.NetworkSet.from_dir('mydir')
        >>> ns.sort()

        Sort by other property
        >>> ns.sort(key= lambda x: x.voltage)
        '''
        self.ntwk_set = sorted(self.ntwk_set, key = key, **kwargs)

    def rand(self,n=1):
        '''
        return `n` random samples from this NetworkSet

        Parameters
        ----------
        n : int
            number of samples to return
        '''
        idx = npy.random.randint(0,len(self), n)
        out = [self.ntwk_set[k] for k in idx]

        if n ==1:
            return out[0]
        else:
            return out

    def filter(self,s):
        '''
        filter networkset based on a string in Network.name

        Notes
        -----
        This is just

        `NetworkSet([k for k in self if s in k.name])`


        Parameters
        -------------
        s: str
            string contained in network elements to be filtered

        Returns
        --------
        ns : NetworkSet


        Examples
        -----------
        >>> ns.filter('monday')
        '''
        return NetworkSet([k for k in self if s in k.name])

    def scalar_mat(self, param='s',order='F'):
        '''
        scalar ndarray representing `param` data vs freq and element idx

        output is a 3d array with axes  (freq, ns_index, port/ri)

        freq is frequency
        ns_index is  index of this networkset
        ports is a flattened re/im components of port index (len =2*nports**2)
        '''
        ntwk=self[0]
        nfreq = len(ntwk)
        # x will have the axes ( frequency,observations, ports)
        x = npy.array([[mf.flatten_c_mat(k.__getattribute__(param)[f]) \
            for k in self] for f in range(nfreq)])

        return x


    def cov(self, **kw):
        '''
        covariance matrix

        shape of output  will be  (nfreq, 2*nports**2, 2*nports**2)
        '''
        smat=self.scalar_mat(**kw)
        return npy.array([npy.cov(k.T) for k in smat])



    @property
    def mean_s_db(self):
        '''
        the mean magnitude in dB.

        note:
                the mean is taken on the magnitude before converted to db, so
                        magnitude_2_db( mean(s_mag))
                which is NOT the same as
                        mean(s_db)
        '''
        ntwk= self.mean_s_mag
        ntwk.s = ntwk.s_db
        return ntwk

    @property
    def std_s_db(self):
        '''
        the standard deviation magnitude in dB.

        note:
                the standard deviation is taken on the magnitude before converted to db, so
                        magnitude_2_db( std(s_mag))
                which is NOT the same as
                        std(s_db)
        '''
        ntwk= self.std_s_mag
        ntwk.s = ntwk.s_db
        return ntwk

    @property
    def inv(self):
        return NetworkSet( [ntwk.inv for ntwk in self.ntwk_set])



    def add_polar_noise(self, ntwk):
        from scipy import stats
        from numpy import frompyfunc

        gimme_norm = lambda x: stats.norm(loc=0,scale=x).rvs(1)[0]
        ugimme_norm = frompyfunc(gimme_norm,1,1)

        s_deg_rv = npy.array(map(ugimme_norm, self.std_s_deg.s_re), dtype=float)
        s_mag_rv = npy.array(map(ugimme_norm, self.std_s_mag.s_re), dtype=float)

        mag = ntwk.s_mag+s_mag_rv
        deg = ntwk.s_deg+s_deg_rv
        ntwk.s = mag* npy.exp(1j*npy.pi/180.*deg)
        return ntwk

    def set_wise_function(self, func, a_property, *args, **kwargs):
        '''
        calls a function on a specific property of the networks in
        this NetworkSet.

        example:
                my_ntwk_set.set_wise_func(mean,'s')
        '''
        return fon(self.ntwk_set, func, a_property, *args, **kwargs)



    def uncertainty_ntwk_triplet(self, attribute,n_deviations=3):
        '''
        returns a 3-tuple of Network objects which contain the
        mean, upper_bound, and lower_bound for the given Network
        attribute.

        Used to save and plot uncertainty information data
        '''
        ntwk_mean = self.__getattribute__('mean_'+attribute)
        ntwk_std = self.__getattribute__('std_'+attribute)
        ntwk_std.s = n_deviations * ntwk_std.s

        upper_bound = (ntwk_mean +ntwk_std)
        lower_bound = (ntwk_mean -ntwk_std)

        return (ntwk_mean, lower_bound, upper_bound)

    def datetime_index(self):
        '''
        Create a datetime index from networks names

        this is just:

        [rf.now_string_2_dt(k.name ) for k in self]


        '''
        return [now_string_2_dt(k.name ) for k in self]


    # io
    def write(self, file=None,  *args, **kwargs):
        '''
        Write the NetworkSet to disk using :func:`~skrf.io.general.write`


        Parameters
        -----------
        file : str or file-object
            filename or a file-object. If left as None then the
            filename will be set to Calibration.name, if its not None.
            If both are None, ValueError is raised.
        \*args, \*\*kwargs : arguments and keyword arguments
            passed through to :func:`~skrf.io.general.write`

        Notes
        ------
        If the self.name is not None and file is  can left as None
        and the resultant file will have the `.ns` extension appended
        to the filename.

        Examples
        ---------
        >>> ns.name = 'my_ns'
        >>> ns.write()

        See Also
        ---------
        skrf.io.general.write
        skrf.io.general.read

        '''
        # this import is delayed until here because of a circular dependency
        from . io.general import write

        if file is None:
            if self.name is None:
                 raise (ValueError('No filename given. You must provide a filename, or set the name attribute'))
            file = self.name

        write(file,self, *args, **kwargs)


    def write_spreadsheet(self, *args, **kwargs):
        '''
        Write contents of network to a spreadsheet, for your boss to use.

        See Also
        ---------
        skrf.io.general.network_2_spreadsheet
        '''
        from . io.general import networkset_2_spreadsheet
        networkset_2_spreadsheet(self, *args, **kwargs)

    def ntwk_attr_2_df(self, attr='s_db',m=0, n=0, *args, **kwargs):
        '''
        Converts an attributes of the Networks within a NetworkSet to a
        Pandas DataFrame

        Examples
        ---------
        df = ns.ntwk_attr_2_df('s_db',m=1,n=0)
        df.to_excel('output.xls') # see Pandas docs for more info

        '''
        from pandas import DataFrame, Series, Index
        index = Index(
            self[0].frequency.f_scaled,
            name='Freq(%s)'%self[0].frequency.unit
            )
        df = DataFrame(
            dict([('%s'%(k.name),
                Series(k.__getattribute__(attr)[:,m,n],index=index))
                for k in self]),
            index = index,
            )
        return df

    def interpolate_from_network(self, ntw_param, x, interp_kind='linear'):
        '''
        Interpolate a Network from a NetworkSet, as a multi-file N-port network.

        Assumes that the NetworkSet contains N-port networks
        with same number of ports N and same number of frequency points.

        These networks differ from an given array parameter `interp_param`,
        which is used to interpolate the returned Network. Length of `interp_param`
        should be equal to the length of the NetworkSet.

        Parameters
        ----------
        ntw_param : (N,) array_like
            A 1-D array of real values. The length of ntw_param must be equal
            to the length of the NetworkSet
        x : real
            Point to evaluate the interpolated network at
        interp_kind: str
            Specifies the kind of interpolation as a string: 'linear', 'nearest', 'zero', 'slinear', 'quadratic', 'cubic'.  Cf :class:`scipy.interpolate.interp1d` for detailled description.
            Default is 'linear'.

        Returns
        -------
        ntw : class:`~skrf.network.Network`
            Network interpolated at x

        '''
        ntw = self[0].copy()
        # Interpolating the scattering parameters
        s = npy.array([self[idx].s for idx in range(len(self))])
        f = interp1d(ntw_param, s, axis=0, kind=interp_kind)
        ntw.s = f(x)

        return ntw


def func_on_networks(ntwk_list, func, attribute='s',name=None, *args,\
        **kwargs):
    '''
    Applies a function to some attribute of a list of networks.


    Returns the result in the form of a Network. This means information
    that may not be s-parameters is stored in the s-matrix of the
    returned Network.

    Parameters
    -------------
    ntwk_list : list of :class:`~skrf.network.Network` objects
            list of Networks on which to apply `func` to
    func : function
            function to operate on `ntwk_list` s-matrices
    attribute : string
            attribute of Network's  in ntwk_list for func to act on
    \*args,\*\*kwargs : arguments and keyword arguments
            passed to func

    Returns
    ---------
    ntwk : :class:`~skrf.network.Network`
            Network with s-matrix the result of func, operating on
            ntwk_list's s-matrices


    Examples
    ----------
    averaging can be implemented with func_on_networks by

    >>> func_on_networks(ntwk_list,mean)

    '''
    data_matrix = \
            npy.array([ntwk.__getattribute__(attribute) for ntwk in ntwk_list])

    new_ntwk = ntwk_list[0].copy()
    new_ntwk.s = func(data_matrix,axis=0,*args,**kwargs)

    if name is not None:
        new_ntwk.name = name

    return new_ntwk

# short hand name for convenience
fon = func_on_networks


def getset(ntwk_dict, s, *args, **kwargs):
    '''
    Creates a :class:`NetworkSet`, of all :class:`~skrf.network.Network`s
    objects in a dictionary that contain `s` in its key. This is useful
    for dealing with the output of
    :func:`~skrf.io.general.load_all_touchstones`, which contains
    Networks grouped by some kind of naming convention.

    Parameters
    ------------
    ntwk_dict : dictionary of Network objects
        network dictionary that contains a set of keys `s`
    s : string
        string contained in the keys of ntwk_dict that are to be in the
        NetworkSet that is returned
    \*args,\*\*kwargs : passed to NetworkSet()

    Returns
    --------
    ntwk_set :  NetworkSet object
        A NetworkSet that made from values of ntwk_dict with `s` in
        their key

    Examples
    ---------
    >>>ntwk_dict = rf.load_all_touchstone('my_dir')
    >>>set5v = getset(ntwk_dict,'5v')
    >>>set10v = getset(ntwk_dict,'10v')
    '''
    ntwk_list = [ntwk_dict[k] for k in ntwk_dict if s in k]
    if len(ntwk_list) > 0:
        return NetworkSet( ntwk_list,*args, **kwargs)
    else:
        print('Warning: No keys in ntwk_dict contain \'%s\''%s)
        return None


def tuner_constellation(name='tuner', singlefreq=76, Z0=50, r_lin = 9, phi_lin=21, TNWformat=True):
    r = npy.linspace(0.1,0.9,r_lin)
    a = npy.linspace(0,2*npy.pi,phi_lin)
    r_, a_ = npy.meshgrid(r,a)
    c_ = r_ *npy.exp(1j * a_)
    g= c_.flatten()
    x =  npy.real(g)
    y =  npy.imag(g)

    if TNWformat :
        TNL = dict()
        # for ii, gi in enumerate(g) :
        for ii, gi in enumerate(g) :
            TNL['pos'+str(ii)] = Network(f = [singlefreq ], s=[[[gi]]], z0=[[Z0]], name=name +'_' + str(ii))
        TNW = NetworkSet(TNL, name=name)
        return TNW, x,y,g
    else :
        return x,y,g


