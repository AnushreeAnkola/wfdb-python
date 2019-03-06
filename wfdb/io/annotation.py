import copy
import os
import re
import pdb

import numpy as np
import pandas as pd

from . import download
from . import _header
from . import record


# The data fields for each individual annotation
ANN_DATA_FIELDS = ('sample', 'symbol', 'subtype', 'chan', 'num', 'aux_note',
    'label_store', 'description')

# Information fields describing the entire annotation set
ANN_INFO_FIELDS = ('record_name', 'extension', 'fs', 'custom_labels')

# Data fields describing the annotation label
ANN_LABEL_FIELDS = ('label_store', 'symbol', 'description')

# All WFDB annotation fields
ANN_FIELDS = ANN_DATA_FIELDS + ANN_INFO_FIELDS

# Allowed types of each Annotation object attribute.
ALLOWED_TYPES = {'record_name': (str), 'extension': (str),
                 'sample': (np.ndarray,), 'symbol': (list, np.ndarray),
                 'subtype': (np.ndarray,), 'chan': (np.ndarray,),
                 'num': (np.ndarray,), 'aux_note': (list, np.ndarray),
                 'fs': _header.float_types, 'label_store': (np.ndarray,),
                 'description':(list, np.ndarray),
                 'custom_labels': (pd.DataFrame, list, tuple)}

str_types = (str, np.str_)

# Standard WFDB annotation file extensions
ANN_EXTENSIONS = pd.DataFrame(data=[
    ('atr', 'Reference ECG annotations', True),

    ('blh', 'Human reviewed beat labels', True),
    ('blm', 'Machine beat labels', False),

    ('alh', 'Human reviewed alarms', True),
    ('alm', 'Machine alarms', False),

    ('qrsc', 'Human reviewed qrs detections', True),
    ('qrs', 'Machine QRS detections', False),

    ('bph', 'Human reviewed BP beat detections', True),
    ('bpm', 'Machine BP beat detections', False),

    #AnnotationClass('alh', 'Human reviewed BP alarms', True),
    #AnnotationClass('alm', 'Machine BP alarms', False),
    # separate ecg and other signal category alarms?
    # Can we use chan to determine the channel it was triggered off?
    ], columns=['extension', 'description', 'human_reviewed']
)

# The allowed integer range for the label_store value in wfdb
# annotations. 0 is used as an indicator.
LABEL_RANGE = (1, 49)

# The standard library annotation label map
ANN_LABELS = pd.DataFrame(data=[
    # 0 is used in the file as an indicator flag.
    (1, 'N', 'Normal beat'),
    (2, 'L', 'Left bundle branch block beat'),
    (3, 'R', 'Right bundle branch block beat'),
    (4, 'a', 'Aberrated atrial premature beat'),
    (5, 'V', 'Premature ventricular contraction'),
    (6, 'F', 'Fusion of ventricular and normal beat'),
    (7, 'J', 'Nodal (junctional) premature beat'),
    (8, 'A', 'Atrial premature contraction'),
    (9, 'S', 'Premature or ectopic supraventricular beat'),
    (10, 'E', 'Ventricular escape beat'),
    (11, 'j', 'Nodal (junctional) escape beat'),
    (12, '/', 'Paced beat'),
    (13, 'Q', 'Unclassifiable beat'),
    (14, '~', 'Signal quality change'),
    (16, '|', 'Isolated QRS-like artifact'),
    (18, 's', 'ST change'),
    (19, 'T', 'T-wave change'),
    (20, '*', 'Systole'),
    (21, 'D', 'Diastole'),
    (22, '"', 'Comment annotation'),
    (23, '=', 'Measurement annotation'),
    (24, 'p', 'P-wave peak'),
    (25, 'B', 'Left or right bundle branch block'),
    (26, '^', 'Non-conducted pacer spike'),
    (27, 't', 'T-wave peak'),
    (28, '+', 'Rhythm change'),
    (29, 'u', 'U-wave peak'),
    (30, '?', 'Learning'),
    (31, '!', 'Ventricular flutter wave'),
    (32, '[', 'Start of ventricular flutter/fibrillation'),
    (33, ']', 'End of ventricular flutter/fibrillation'),
    (34, 'e', 'Atrial escape beat'),
    (35, 'n', 'Supraventricular escape beat'),
    (36, '@', 'Link to external data (aux_note contains URL)'),
    (37, 'x', 'Non-conducted P-wave (blocked APB)'),
    (38, 'f', 'Fusion of paced and normal beat'),
    (39, '(', 'Waveform onset'),
    (40, ')', 'Waveform end'),
    (41, 'r', 'R-on-T premature ventricular contraction'),
    ], columns=['label_store', 'symbol', 'description']
)

ANN_LABELS.set_index(ANN_LABELS['label_store'].values, inplace=True)


class Annotation(object):
    """
    The class representing WFDB annotations.

    Annotation objects can be created using the initializer, or by
    reading a WFDB annotation file with `rdann`.

    The attributes of the Annotation object give information about the
    annotation as specified by:
    https://www.physionet.org/physiotools/wag/annot-5.htm

    Call `show_ann_labels()` to see the standard annotation label
    definitions. When writing annotation files, please adhere to these
    standards for all annotation definitions present in this table, and
    define the `custom_labels` field for items that are not present.

    Supplementary text used to label annotations should go in the
    'aux_note' field rather than the 'symbol' field.

    Examples
    --------
    >>> ann1 = wfdb.Annotation(record_name='rec1', extension='atr',
                               sample=[10,20,400], symbol=['N','N','['],
                               aux_note=[None, None, 'Serious Vfib'])

    """
    def __init__(self, record_name, extension, sample, symbol=None,
                 subtype=None, chan=None, num=None, aux_note=None,
                 fs=None, label_store=None, description=None,
                 custom_labels=None):
        """
        Parameters
        ----------
        record_name : str
            The base file name (without extension) of the record that
            the annotation set is associated with.
        extension : str
            The file extension of the file the annotation is stored in.
        sample : numpy array
            A numpy array containing the annotation locations in samples
            relative to the beginning of the record.
        symbol : numpy array, optional
            The symbols used to display the annotation labels.
        subtype : numpy array, optional
            A numpy array containing the marked class/category of each
            annotation.
        chan : numpy array, optional
            A numpy array containing the signal channel associated with
            each annotation.
        num : numpy array, optional
            A numpy array containing the labelled annotation number for
            each annotation.
        aux_note : list, optional
            A list containing the auxiliary information string (or None for
            annotations without notes) for each annotation.
        fs : int, or float, optional
            The sampling frequency of the record.
        label_store : numpy array, optional
            The integer value used to store/encode each annotation label
        description : list, optional
            A list containing the descriptive string of each annotation label.
        custom_labels : pandas dataframe, optional
            The custom annotation labels defined in the annotation file
            Maps the relationship between the three label fields. The
            DataFrame must have the three columns:
            ['label_store', 'symbol', 'description']

        """
        self.record_name = record_name
        self.extension = extension
        self.sample = sample
        self.symbol = symbol
        self.subtype = subtype
        self.chan = chan
        self.num = num
        self.aux_note = aux_note
        self.fs = fs
        self.label_store = label_store
        self.description = description
        self.custom_labels = custom_labels

    def __eq__(self, other):
        "Equal comparison operator for objects of this type"
        att1 = self.__dict__
        att2 = other.__dict__

        if set(att1.keys()) != set(att2.keys()):
            return False

        for k in att1.keys():
            v1 = att1[k]
            v2 = att2[k]

            if type(v1) != type(v2):
                print(k)
                return False

            if isinstance(v1, np.ndarray):
                if not np.array_equal(v1, v2):
                    print(k)
                    return False
            elif isinstance(v1, pd.DataFrame):
                if not v1.equals(v2):
                    print(k)
                    return False
            else:
                if v1 != v2:
                    print(k)
                    return False

        return True

    def apply_range(self, sampfrom=0, sampto=None):
        """
        Filter the annotation attributes to keep only items between the
        desired sample values

        """
        sampto = sampto or self.sample[-1]

        kept_inds = np.intersect1d(np.where(self.sample>=sampfrom),
                                   np.where(self.sample<=sampto))

        for field in ['sample', 'label_store', 'subtype', 'chan', 'num']:
            setattr(self, field, getattr(self, field)[kept_inds])

        self.aux_note = [self.aux_note[i] for i in kept_inds]

    def contained_data_fields(self):
        """
        Return the data fields possessed by this object
        """
        return [f for f in ANN_DATA_FIELDS if hasattr(self, f)]

    def wrann(self, write_fs=False, write_dir=''):
        """
        Write a WFDB annotation file from this object.

        !!! Should we force an argument to choose the label field used?

        Parameters
        ----------
        write_fs : bool, optional
            Whether to write the `fs` attribute to the file.

        Notes
        -----
        The label_store field will be generated if necessary

        """

        # Check the presence of vital fields
        contained_label_fields = self._contained_label_fields()
        if not contained_label_fields:
            raise Exception('At least one annotation label field is required to write the annotation: ', ANN_LABEL_FIELDS)
        for field in ['record_name', 'extension']:
            if getattr(self, field) is None:
                raise Exception('Missing required field for writing annotation file: ',field)

        # Check the validity of individual fields
        self.check_fields()

        # Standardize the format of the custom_labels field
        self._custom_labels_to_df()

        # Create the label map used in this annotaion
        self._create_label_map()

        # Set the label_store field if necessary
        if 'label_store' not in contained_label_fields:
            self.convert_label_attribute(source_field=contained_label_fields[0],
                                         target_field='label_store')

        # Check the cohesion of the fields
        self.check_field_cohesion()

        # Write the header file using the specified fields
        self.wr_ann_file(write_fs=write_fs, write_dir=write_dir)

    def _contained_label_fields(self):
        """
        Get the label fields contained in the object
        """
        return [field for field in ANN_LABEL_FIELDS if getattr(self, field)]

    def check_fields(self):
        """
        Check the set fields of the annotation object
        """
        for field in ANN_FIELDS:
            if hasattr(self, field):
                self.check_field(field)

    def check_field(self, field):
        """
        Check a particular annotation field
        """

        item = getattr(self, field)

        if not isinstance(item, ALLOWED_TYPES[field]):
            raise TypeError("The '{}' field must be one of the following types:".format(field),
                ALLOWED_TYPES[field])

        # Numerical integer annotation fields: sample, label_store, sub,
        # chan, num
        if ALLOWED_TYPES[field] == (np.ndarray):
            record.check_np_array(item=item, field_name=field, ndim=1,
                                  parent_class=np.integer, channel_num=None)

        # Field specific checks
        if field == 'record_name':
            if re.search('[^-\w]', self.record_name):
                raise ValueError('record_name must only comprise of letters, digits, hyphens, and underscores.')
        elif field == 'extension':
            if re.search('[^a-zA-Z]', self.extension):
                raise ValueError('extension must only comprise of letters.')
        elif field == 'fs':
            if self.fs <= 0:
                raise ValueError('The fs field must be a non-negative number')
        elif field == 'custom_labels':
            # The role of this section is just to check the elements of
            # this item, without utilizing any other fields. No format
            # conversion or free value looksups etc are done.

            # Check the structure of the subelements
            if isinstance(item, pd.DataFrame):
                column_names = list(item)
                if 'symbol' in column_names and 'description' in column_names:
                    if 'label_store' in column_names:
                        label_store = list(item['label_store'].values)
                    else:
                        label_store = None
                    symbol = item['symbol'].values
                    description = item['description'].values
                else:
                    raise ValueError(''.join(['If the '+field+' field is pandas dataframe, its columns',
                                             ' must be one of the following:\n-[label_store, symbol, description]',
                                             '\n-[symbol, description]']))
            else:
                if set([len(i) for i in item]) == {2}:
                    label_store = None
                    symbol = [i[0] for i in item]
                    description = [i[1] for i in item]
                elif set([len(i) for i in item]) == {3}:
                    label_store = [i[0] for i in item]
                    symbol = [i[1] for i in item]
                    description = [i[2] for i in item]
                else:
                    raise ValueError(''.join(['If the '+field+' field is an array-like object, its subelements',
                                             ' must be one of the following:\n- tuple triplets storing: ',
                                             '(label_store, symbol, description)\n- tuple pairs storing: ',
                                             '(symbol, description)']))

            # Check the values of the subelements
            if label_store:
                if len(item) != len(set(label_store)):
                    raise ValueError('The label_store values of the '+field+' field must be unique')

                if min(label_store) < 1 or max(label_store) > 49:
                    raise ValueError('The label_store values of the custom_labels field must be between 1 and 49')

            if len(item) != len(set(symbol)):
                raise ValueError('The symbol values of the '+field+' field must be unique')

            for i in range(len(item)):
                if label_store:
                    if not hasattr(label_store[i], '__index__'):
                        raise TypeError('The label_store values of the '+field+' field must be integer-like')

                if not isinstance(symbol[i], str_types) or len(symbol[i]) not in [1,2,3]:
                    raise ValueError('The symbol values of the '+field+' field must be strings of length 1 to 3')

                if bool(re.search('[ \t\n\r\f\v]', symbol[i])):
                    raise ValueError('The symbol values of the '+field+' field must not contain whitespace characters')

                if not isinstance(description[i], str_types):
                    raise TypeError('The description values of the '+field+' field must be strings')

                # Would be good to enfore this but existing garbage annotations have tabs and newlines...
                #if bool(re.search('[\t\n\r\f\v]', description[i])):
                #    raise ValueError('The description values of the '+field+' field must not contain tabs or newlines')

        # The string fields
        elif field in ['symbol', 'description', 'aux_note']:
            uniq_elements = set(item)

            for e in uniq_elements:
                if not isinstance(e, str_types):
                    raise TypeError("Subelements of the '{}' field must be strings".format(field))

            if field == 'symbol':
                for e in uniq_elements:
                    if len(e) not in [1,2,3]:
                        raise ValueError("Subelements of the '{}' field must be strings of length 1 to 3".format(field))
                    if bool(re.search('[ \t\n\r\f\v]', e)):
                        raise ValueError("Subelements of the '{}' field may not contain whitespace characters".format(field))
            else:
                for e in uniq_elements:
                    if bool(re.search('[\t\n\r\f\v]', e)):
                        raise ValueError("Subelements of the '{}' field may not contain tabs or newlines".format(field))

        elif field == 'sample':
            if len(self.sample) == 1:
                sampdiffs = np.array([self.sample[0]])
            elif len(self.sample) > 1:
                sampdiffs = np.concatenate(([self.sample[0]], np.diff(self.sample)))
            else:
                raise ValueError("The 'sample' field must be a numpy array with length greater than 0")
            if min(self.sample) < 0 :
                raise ValueError("The 'sample' field must only contain non-negative integers")
            if min(sampdiffs) < 0 :
                raise ValueError("The 'sample' field must contain monotonically increasing sample numbers")
            if max(sampdiffs) > 2147483648:
                raise ValueError('WFDB annotation files cannot store sample differences greater than 2**31')

        elif field == 'label_store':
            if min(item) < 1 or max(item) > 49:
                raise ValueError('The label_store values must be between 1 and 49')

        # The C WFDB library stores num/sub/chan as chars.
        elif field == 'subtype':
            # signed character
            if min(self.subtype) < 0 or max(self.subtype) >127:
                raise ValueError("The 'subtype' field must only contain non-negative integers up to 127")
        elif field == 'chan':
            # un_signed character
            if min(self.chan) < 0 or max(self.chan) >255:
                raise ValueError("The 'chan' field must only contain non-negative integers up to 255")
        elif field == 'num':
            # signed character
            if min(self.num) < 0 or max(self.num) >127:
                raise ValueError("The 'num' field must only contain non-negative integers up to 127")

        return

    def check_field_cohesion(self):
        """
        Check that the content and structure of different fields are
        consistent with one another.
        """
        contained_label_fields = self._contained_label_fields

        # Ensure all written annotation fields have the same length
        n_annots = len(self.sample)

        for field in ['sample', 'num', 'subtype', 'chan', 'aux_note'] + contained_label_fields:
            if getattr(self, field):
                if len(getattr(self, field)) != n_annots:
                    raise ValueError("The lengths of the 'sample' and '{}' fields do not match".format(field))

        # Ensure all label fields are consistent with one another.
        # Only need to check if at least 2 fields.
        if len(contained_label_fields) >1:



        # Ensure all label fields are defined by the label map. This has
        # to be checked because it is possible the user defined (or
        # lack of) custom_labels does not capture all the labels present.
        for field in contained_label_fields:
            defined_values = self.__label_map__[field].values

            if set(getattr(self, field)) - set(defined_values) != set():
                raise ValueError('\n'.join([
                    "\nThe '{}' field contains elements not encoded in the stardard WFDB annotation labels, or this object's custom_labels field".format(field),
                    '- To see the standard WFDB annotation labels, call: show_ann_labels()',
                    '- To transfer non-encoded symbol items into the aux_note field, call: self.sym_to_aux()',
                    '- To define custom labels, set the custom_labels field as a list of tuple triplets with format: (label_store, symbol, description)']))




        # Ensure the lab map is accurate
        if self.__label_map__:

        else:
            label_map = []



        return

    def _custom_labels_to_df(self):
        """
        Convert the `custom_labels` attribute, if present, into a pandas
        dataframe, if it is not already.

        - Does nothing if there are no custom labels defined.
        - Does nothing if custom_labels is already a df with all 3 columns
        - If custom_labels is an iterable of pairs/triplets, this
          function will convert it into a df.

        If it contains two fields, assume them to represent 'symbol' and
        'description'. If it contains three, then they represent
        ANN_LABEL_FIELDS.

        Do not worry about overwriting the attribute, because the
        information is still the same.

        """
        if not self.custom_labels:
            return

        self.check_field('custom_labels')

        # Convert to dataframe if not already
        if not isinstance(self.custom_labels, pd.DataFrame):
            if len(self.custom_labels[0]) == 2:
                symbol = self._get_custom_labels_attribute('symbol')
                description = self._get_custom_labels_attribute('description')
                self.custom_labels = pd.DataFrame({'symbol': symbol,
                    'description': description})
            else:
                label_store = self._get_custom_labels_attribute('label_store')
                symbol = self._get_custom_labels_attribute('symbol')
                description = self._get_custom_labels_attribute('description')
                self.custom_labels = pd.DataFrame({'label_store':label_store,
                    'symbol': symbol, 'description': description})

    def _get_available_label_stores(self):
        """
        Get the label store values that may be used for writing this
        annotation. The function will choose one of the contained
        attributes by checking availability in the order: label_store,
        symbol, description.

        Available store values include:
        - the undefined values in the standard wfdb labels
        - the store values not used in the current annotation object.
        - the store values whose standard wfdb symbols/descriptions
          match those of the custom labels (if custom_labels exists)

        """
        # Choose a field to use to get available labels stores.
        for field in ANN_LABEL_FIELDS:
            if getattr(self, field):
                usefield = field
                break
        else:
            raise ValueError('No label fields are defined. At least one of the following is required: ', ANN_LABEL_FIELDS)

        # We are using 'label_store', the steps are slightly different.

        # Get the unused label_store values
        if usefield == 'label_store':
            unused_label_stores = set(ANN_LABELS['label_store'].values) - set(self.label_store)
        else:
            # the label_store values from the standard wfdb annotation labels
            # whose symbols are not contained in this annotation
            unused_field = set(ANN_LABELS[usefield].values) - getattr(self, usefield)
            unused_label_stores = ANN_LABELS.loc[ANN_LABELS[usefield] in unused_field, 'label_store'].values

        # Get the standard wfdb label_store values overwritten by
        # the custom_labels if any
        if self.custom_labels is not None:
            custom_field = set(self._get_custom_labels_attribute(usefield))
            if usefield == 'label_store':
                overwritten_label_stores = set(custom_field).intersection(set(ANN_LABELS['label_store']))
            else:
                overwritten_fields = set(custom_field).intersection(set(ANN_LABELS[usefield]))
                overwritten_label_stores = ANN_LABELS.loc[ANN_LABELS[usefield] in overwritten_fields, 'label_store'].values
        else:
            overwritten_label_stores = set()

        # The label_store values in the allowed range, that are not
        # defined in the standard WFDB label map
        undefined_label_stores = self.get_undefined_label_stores()
        # Final available label stores = undefined + unused + overwritten
        available_label_stores = set(undefined_label_stores).union(set(unused_label_stores)).union(overwritten_label_stores)

        return available_label_stores

    def _get_custom_labels_attribute(self, attribute):
        """
        Get a list of the custom_labels attribute. ie. label_store,
        symbol, or description.

        The custom_labels variable could be in a number of formats. This
        helper function returns the desired attribute regardless of the
        format.
        """
        if attribute not in ANN_LABEL_FIELDS:
            raise ValueError('Invalid attribute specified')

        if isinstance(self.custom_labels, pd.DataFrame):
            if 'label_store' not in list(self.custom_labels):
                raise ValueError('label_store is not defined in custom_labels')
            a = list(self.custom_labels[attribute].values)
        else:
            if len(self.custom_labels[0]) == 2:
                if attribute == 'label_store':
                    raise ValueError('label_store is not defined in custom_labels')
                elif attribute == 'symbol':
                    a = [l[0] for l in self.custom_labels]
                elif attribute == 'description':
                    a = [l[1] for l in self.custom_labels]
            else:
                if attribute == 'label_store':
                    a = [l[0] for l in self.custom_labels]
                elif attribute == 'symbol':
                    a = [l[1] for l in self.custom_labels]
                elif attribute == 'description':
                    a = [l[2] for l in self.custom_labels]

        return a

    def _create_label_map(self):
        """
        Create a mapping df for the annotation labels, based on
        ANN_LABELS and self.custom_labels if it exists. Sets the
        computed map in the `__label_map__` attribute.

        The mapping table is composed of the entire WFDB standard
        annotation table, overwritten/appended with custom_labels if
        any.

        If the `custom_labels` attribute does not yet have the
        `label_store` column, this function chooses appropriate values,
        but does not save these values in the same attribute; it only
        saves the final result in the __label_map__ attribute.

        """
        label_map =  ANN_LABELS.copy()

        # Need to deal with custom labels
        if self.custom_labels:
            # Ensure it is in df format
            self._custom_labels_to_df()
            # If label_store is not explicitly set in custom_labels,
            # we have to choose appropriate values
            if 'label_store' not in list(custom_labels):
                # Check whether we need to overwrite unused values, or
                # if we can just use the undefined values.
                undefined_label_stores = get_undefined_label_stores()
                if self.custom_labels.shape[0] > len(undefined_label_stores):
                    available_label_stores = self._get_available_label_stores()
                else:
                    available_label_stores = undefined_label_stores
                # Enforce max number of custom labels
                if self.custom_labels.shape[0] > len(available_label_stores):
                    raise ValueError('There are more custom_label definitions than storage values available for them.')

            custom_labels = self.custom_labels.copy()
            custom_labels['label_store'] = available_label_stores[:self.custom_labels.shape[0]]

            # Input the custom_labels label store values into the final
            # label map
            for i in custom_labels.index:
                label_map.loc[i] = custom_labels.loc[i]
            # Arrange the columns and set the index to label_store
            label_map = label_map[list(ANN_LABEL_FIELDS)]
            label_map.set_index(label_map['label_store'].values, inplace=True)

        self.__label_map__ = label_map


    def wr_ann_file(self, write_fs, write_dir=''):
        """
        Calculate the bytes used to encode an annotation set and
        write them to an annotation file
        """

        # Calculate the fs bytes to write if present and desired to write
        if write_fs:
            fs_bytes = self.calc_fs_bytes()
        else:
            fs_bytes = []
        # Calculate the custom_labels bytes to write if present
        cl_bytes = self.calc_cl_bytes()
        # Calculate the core field bytes to write
        core_bytes = self.calc_core_bytes()

        # Mark the end of the special annotation types if needed
        if fs_bytes == [] and cl_bytes == []:
            end_special_bytes = []
        else:
            end_special_bytes = [0, 236, 255, 255, 255, 255, 1, 0]

        # Write the file
        with open(os.path.join(write_dir, self.record_name+'.'+self.extension),
                  'wb') as f:
            # Combine all bytes to write: fs (if any), custom
            # annotations (if any), main content, file terminator
            np.concatenate((fs_bytes, cl_bytes, end_special_bytes, core_bytes,
                            np.array([0,0]))).astype('u1').tofile(f)

        return

    def calc_fs_bytes(self):
        """
        Calculate the bytes written to the annotation file for the fs
        field

        """
        if self.fs is None:
            return []

        # Initial indicators of encoding fs
        data_bytes = [0, 88, 0, 252, 35, 35, 32, 116, 105, 109, 101, 32, 114,
                      101, 115, 111, 108, 117, 116, 105, 111, 110, 58, 32]

        # Check if fs is close enough to int
        if isinstance(self.fs, float):
            if round(self.fs,8) == float(int(self.fs)):
                self.fs = int(self.fs)

        fschars = str(self.fs)
        ndigits = len(fschars)

        for i in range(ndigits):
            data_bytes.append(ord(fschars[i]))

        # Fill in the aux_note length
        data_bytes[2] = ndigits + 20

        # odd number of digits
        if ndigits % 2:
            data_bytes.append(0)

        return np.array(data_bytes).astype('u1')

    def calc_cl_bytes(self):
        """
        Calculate the bytes written to the annotation file for the
        custom_labels field
        """

        if self.custom_labels is None:
            return []

        # The start wrapper: '0 NOTE length aux_note ## annotation type definitions'
        headbytes = [0,88,30,252,35,35,32,97,110,110,111,116,97,116,105,111,110,32,116,
                     121,112,101,32,100,101,102,105,110,105,116,105,111,110,115]

        # The end wrapper: '0 NOTE length aux_note ## end of definitions' followed by SKIP -1, +1
        tailbytes =  [0,88,21,252,35,35,32,101,110,100,32,111,102,32,100,101,102,105,110,
                      105,116,105,111,110,115,0]

        custom_bytes = []

        for i in self.custom_labels.index:
            custom_bytes += custom_triplet_bytes(list(self.custom_labels.loc[i, list(ANN_LABEL_FIELDS)]))

        return np.array(headbytes + custom_bytes + tailbytes).astype('u1')

    def calc_core_bytes(self):
        """
        Convert all used annotation fields into bytes to write
        """
        # The difference sample to write
        if len(self.sample) == 1:
            sampdiff = np.array([self.sample[0]])
        else:
            sampdiff = np.concatenate(([self.sample[0]], np.diff(self.sample)))

        # Create a copy of the annotation object with a compact version
        # of fields to write
        compact_annotation = copy.deepcopy(self)
        compact_annotation._compact_fields()

        # The optional fields to be written. Write if they are not None
        # or all empty
        extra_write_fields = []

        for field in ['num', 'subtype', 'chan', 'aux_note']:
            if not isblank(getattr(compact_annotation, field)):
                extra_write_fields.append(field)

        data_bytes = []

        # Iterate across all fields one index at a time
        for i in range(len(sampdiff)):

            # Process the samp (difference) and sym items
            data_bytes.append(field2bytes('samptype', [sampdiff[i], self.symbol[i]]))

            # Process the extra optional fields
            for field in extra_write_fields:
                value = getattr(compact_annotation, field)[i]
                if value is not None:
                    data_bytes.append(field2bytes(field, value))

        # Flatten and convert to correct format
        data_bytes = np.array([item for sublist in data_bytes for item in sublist]).astype('u1')

        return data_bytes


    def _compact_fields(self):
        """
        Compact all of the object's fields so that the output
        annotation file writes as few bytes as possible
        """
        # Number of annotations
        n_annots = len(self.sample)

        # Chan and num carry over previous fields. Get lists of as few
        # elements to write as possible
        self.chan = compact_carry_field(self.chan)
        self.num = compact_carry_field(self.num)

        # Elements of 0 (default) do not need to be written for subtype.
        # num and sub are signed in original c package...
        if self.subtype is not None:
            if isinstance(self.subtype, list):
                for i in range(n_annots):
                    if self.subtype[i] == 0:
                        self.subtype[i] = None
                if np.array_equal(self.subtype, [None]*n_annots):
                    self.subtype = None
            else:
                zero_inds = np.where(self.subtype==0)[0]
                if len(zero_inds) == n_annots:
                    self.subtype = None
                else:
                    self.subtype = list(self.subtype)
                    for i in zero_inds:
                        self.subtype[i] = None

        # Empty aux_note strings are not written
        if self.aux_note is not None:
            for i in range(n_annots):
                if self.aux_note[i] == '':
                    self.aux_note[i] = None
            if np.array_equal(self.aux_note, [None]*n_annots):
                self.aux_note = None


    def sym_to_aux(self):
        # Move non-encoded symbol elements into the aux_note field
        self.check_field('symbol')

        # Non-encoded symbols
        label_table_map = self._create_label_map(inplace=False)
        external_syms = set(self.symbol) - set(label_table_map['symbol'].values)

        if external_syms == set():
            return

        if self.aux_note is None:
            self.aux_note = ['']*len(self.sample)

        for ext in external_syms:
            for i in [i for i,x in enumerate(self.symbol) if x == ext]:
                if not self.aux_note[i]:
                    self.aux_note[i] = self.symbol[i]
                else:
                    self.aux_note[i] = self.symbol[i]+' '+self.aux_note[i]
                self.symbol[i] = '"'
        return

    def get_contained_labels(self):
        """
        Get the set of unique labels contained in this annotation set,
        along with their frequency of occurences.

        Returns a data frame with one column for each contained label
        field, and one for the number of occurences.

        Examples
        --------
        >>> # Read an annotation set
        >>> annotation = wfdb.rdann('b001', 'atr', pb_dir='cebsdb')
        >>> # Get the contained labels
        >>> contained_labels = annotation.get_contained_labels()
        """
        if self.custom_labels:
            self._custom_labels_to_df()

        self.check_field_cohesion()

        # Merge the standard wfdb labels with the custom labels.
        # custom labels values overwrite standard wfdb if overlap.
        if self.custom_labels:
            for i in custom_labels.index:
                label_map.loc[i] = custom_labels.loc[i]
            # This doesn't work...
            # label_map.loc[custom_labels.index] = custom_labels.loc[custom_labels.index]

        # Get the labels using one of the label features
        if self.label_store:
            index_vals = set(self.label_store)
            reset_index = False
            values, counts = np.unique(self.label_store, return_counts=True)
        elif self.symbol:
            index_vals = set(self.symbol)
            label_map.set_index(label_map['symbol'].values, inplace=True)
            reset_index = True
            values, counts = np.unique(self.symbol, return_counts=True)
        elif self.description:
            index_vals = set(self.description)
            label_map.set_index(label_map['description'].values, inplace=True)
            reset_index = True
            values, counts = np.unique(self.description, return_counts=True)
        else:
            raise Exception('No annotation labels contained in object')

        contained_labels = label_map.loc[index_vals, :]

        # Add the counts
        for i in range(len(counts)):
            contained_labels.loc[values[i], 'n_occurrences'] = counts[i]
        contained_labels['n_occurrences'] = pd.to_numeric(contained_labels['n_occurrences'], downcast='integer')

        if reset_index:
            contained_labels.set_index(contained_labels['label_store'].values,
                                       inplace=True)

        return contained_labels

    def _set_data_fields(self, data_fields, rm_remainder=True):
        """
        Set the specified annotation data fields.

        Remove the remaining undesired fields if specified.

        """
        # The fields that need to be set. Should only be label fields.
        set_fields = set(data_fields) - set(self.contained_data_fields())
        # Only label fields can be set from other label fields
        if not set(set_fields).issubset(set(ANN_LABEL_FIELDS)):
            raise ValueError('Unable to set non-label fields that are not already contained.')

        self.set_label_fields(label_fields=set_fields)

        # Remove the unwanted fields if specified
        if rm_remainder:
            for f in set(self.contained_data_fields()) - set(data_fields):
                delattr(self, f)

    def set_label_fields(self, label_fields):
        """
        Set the specified annotation label fields using already existing
        label fields.

        IMPLEMENT

        """
        # Label fields that the object already has, and can use
        contained_label_fields = self._contained_label_fields()

        if not contained_label_fields:
            raise Exception('No annotation labels contained in object')

        # Set the missing fields
        for field in label_fields:
            if not getattr(self, field):
                self.convert_label_attribute(contained_elements[0], field)



    def set_label_elements(self, wanted_label_elements):
        """
        DEPRECATE

        Set one or more label elements based on
        at least one of the others

        DEPRECATE
        """
        if isinstance(wanted_label_elements, str):
            wanted_label_elements = [wanted_label_elements]

        # Figure out which desired label elements are missing
        missing_elements = [e for e in wanted_label_elements if getattr(self, e) is None]

        contained_elements = [e for e in ANN_LABEL_FIELDS if getattr(self, e )is not None]

        if not contained_elements:
            raise Exception('No annotation labels contained in object')

        for e in missing_elements:
            self.convert_label_attribute(contained_elements[0], e)

        unwanted_label_elements = set(ANN_LABEL_FIELDS - set(wanted_label_elements))

        self._rm_attributes(unwanted_label_elements)

        return







    def convert_label_attribute(self, source_field, target_field):
        """
        UPDATE

        Convert one label attribute (label_store, symbol, or
        description) to another. Creates a mapping df on the fly based
        on ANN_LABELS and self.custom_labels

        Parameters
        ----------
        source_field : str
            The source label attribute.
        target_field : str
            The destination label attribute

        """
        if inplace and not overwrite:
            if getattr(self, target_field) is not None:
                return

        label_map = self._create_label_map(inplace=False)
        label_map.set_index(source_field, inplace=True)

        target_item = label_map.loc[getattr(self, source_field), target_field].values

        if target_field != 'label_store':
            # Should already be int64 dtype if target is label_store
            target_item = list(target_item)

        setattr(self, target_field, target_item)

    def _rm_attributes(self, attributes):
        """
        Remove the specified attributes from the object.
        """
        if isinstance(attributes, str):
            attributes = [attributes]
        for a in attributes:
            delattr(self, a)

    def to_df(self, fields=None):
        """
        Create a pandas DataFrame from the Annotation object

        """
        fields = fields or ANN_DATA_FIELDS[:6]

        df = pd.DataFrame(data={'sample':self.sample, 'symbol':self.symbol,
            'subtype':self.subtype, 'chan':self.chan, 'num':self.num,
            'aux_note':self.aux_note}, columns=['sample', 'symbol', 'subtype',
            'chan', 'aux_note'])
        return df


def label_triplets_to_df(triplets):
    """
    Get a pd dataframe from a tuple triplets
    used to define annotation labels.

    The triplets should come in the
    form: (label_store, symbol, description)
    """

    label_df = pd.DataFrame({'label_store':np.array([t[0] for t in triplets],
                                                    dtype='int'),
                             'symbol':[t[1] for t in triplets],
                             'description':[t[2] for t in triplets]})

    label_df.set_index(label_df['label_store'].values, inplace=True)
    label_df = label_df[list(ANN_LABEL_FIELDS)]

    return label_df


def custom_triplet_bytes(custom_triplet):
    """
    Convert triplet of [label_store, symbol, description] into bytes
    for defining custom labels in the annotation file
    """
    # Structure: 0, NOTE, len(aux_note), aux_note, codenumber, space, codesymbol, space, description, (0 null if necessary)
    # Remember, aux_note string includes 'number(s)<space><symbol><space><description>''
    annbytes = [0, 88, len(custom_triplet[2]) + 3 + len(str(custom_triplet[0])), 252] + [ord(c) for c in str(custom_triplet[0])] \
               + [32] + [ord(custom_triplet[1])] + [32] + [ord(c) for c in custom_triplet[2]]

    if len(annbytes) % 2:
        annbytes.append(0)

    return annbytes


# Tests whether the item is blank
def isblank(x):
    if x is None:
        return True
    elif isinstance(x, list):
        if set(x) == set([None]):
            return True
    return False


def compact_carry_field(full_field):
    """
    Return the compact list version of a list/array of an
    annotation field that has previous values carried over
    (chan or num)
    - The first sample is 0 by default. Only set otherwise
      if necessary.
    - Only set fields if they are different from their prev
      field
    """

    # Keep in mind that the field may already be compact or None

    if full_field is None:
        return None

    # List of same length. Place None where element
    # does not need to be written
    compact_field = [None]*len(full_field)

    prev_field = 0

    for i in range(len(full_field)):
        current_field = full_field[i]
        if current_field != prev_field:
            compact_field[i] = current_field
            prev_field = current_field

    # May further simplify
    if np.array_equal(compact_field, [None]*len(full_field)):
        compact_field = None

    return compact_field


# Convert an annotation field into bytes to write
def field2bytes(field, value):

    data_bytes = []

    # samp and sym bytes come together
    if field == 'samptype':
        # Numerical value encoding annotation symbol
        typecode = ANN_LABELS.loc[ANN_LABELS['symbol']==value[1], 'label_store'].values[0]

        # sample difference
        sd = value[0]

        # Add SKIP element if value is too large for single byte
        if sd>1023:
            # 8 bytes in total:
            # - [0, 59>>2] indicates SKIP
            # - Next 4 gives sample difference
            # - Final 2 give 0 and sym
            data_bytes = [0, 236, (sd&16711680)>>16, (sd&4278190080)>>24, sd&255, (sd&65280)>>8, 0, 4*typecode]
        # Just need samp and sym
        else:
            # - First byte stores low 8 bits of samp
            # - Second byte stores high 2 bits of samp
            #   and sym
            data_bytes = [sd & 255, ((sd & 768) >> 8) + 4*typecode]

    elif field == 'num':
        # First byte stores num
        # second byte stores 60*4 indicator
        data_bytes = [value, 240]
    elif field == 'subtype':
        # First byte stores subtype
        # second byte stores 61*4 indicator
        data_bytes = [value, 244]
    elif field == 'chan':
        # First byte stores num
        # second byte stores 62*4 indicator
        data_bytes = [value, 248]
    elif field == 'aux_note':
        # - First byte stores length of aux_note field
        # - Second byte stores 63*4 indicator
        # - Then store the aux_note string characters
        data_bytes = [len(value), 252] + [ord(i) for i in value]
        # Zero pad odd length aux_note strings
        if len(value) % 2:
            data_bytes.append(0)

    return data_bytes


def wrann(record_name, extension, sample, symbol=None, subtype=None, chan=None,
          num=None, aux_note=None, label_store=None, fs=None,
          custom_labels=None, write_dir=''):
    """
    Write a WFDB annotation file.

    Specify at least the following:

    - The record name of the WFDB record (record_name)
    - The annotation file extension (extension)
    - The annotation locations in samples relative to the beginning of
      the record (sample)
    - Either the numerical values used to store the labels
      (`label_store`), or more commonly, the display symbols of each
      label (`symbol`).

    Parameters
    ----------
    record_name : str
        The string name of the WFDB record to be written (without any file
        extensions).
    extension : str
        The string annotation file extension.
    sample : numpy array
        A numpy array containing the annotation locations in samples relative to
        the beginning of the record.
    symbol : list, or numpy array, optional
        The symbols used to display the annotation labels. List or numpy array.
        If this field is present, `label_store` must not be present.
    subtype : numpy array, optional
        A numpy array containing the marked class/category of each annotation.
    chan : numpy array, optional
        A numpy array containing the signal channel associated with each
        annotation.
    num : numpy array, optional
        A numpy array containing the labelled annotation number for each
        annotation.
    aux_note : list, optional
        A list containing the auxiliary information string (or None for
        annotations without notes) for each annotation.
    label_store : numpy array, optional
        A numpy array containing the integer values used to store the
        annotation labels. If this field is present, `symbol` must not be
        present.
    fs : int, or float, optional
        The numerical sampling frequency of the record to be written to the file.
    custom_labels : pandas dataframe, optional
        The map of custom defined annotation labels used for this annotation, in
        addition to the standard WFDB annotation labels. Custom labels are
        defined by two or three fields:

        - The integer values used to store custom annotation labels in the file
          (optional)
        - Their short display symbols
        - Their long descriptions.

        This input argument may come in four formats:

        1. A pandas.DataFrame object with columns:
           ['label_store', 'symbol', 'description']
        2. A pandas.DataFrame object with columns: ['symbol', 'description']
           If this option is chosen, label_store values are automatically chosen.
        3. A list or tuple of tuple triplets, with triplet elements
           representing: (label_store, symbol, description).
        4. A list or tuple of tuple pairs, with pair elements representing:
           (symbol, description). If this option is chosen, label_store values
           are automatically chosen.

        If the `label_store` field is given for this function, and
        `custom_labels` is defined, `custom_labels` must contain `label_store`
        in its mapping. ie. it must come in format 1 or 3 above.
    write_dir : str, optional
        The directory in which to write the annotation file

    Notes
    -----
    This is a gateway function, written as a simple way to write WFDB annotation
    files without needing to explicity create an Annotation object. You may also
    create an Annotation object, manually set its attributes, and call its
    `wrann` instance method.

    Each annotation stored in a WFDB annotation file contains a sample field and
    a label field. All other fields may or may not be present.

    Examples
    --------
    >>> # Read an annotation as an Annotation object
    >>> annotation = wfdb.rdann('b001', 'atr', pb_dir='cebsdb')
    >>> # Write a copy of the annotation file
    >>> wfdb.wrann('b001', 'cpy', annotation.sample, annotation.symbol)

    """

    # Create Annotation object
    annotation = Annotation(record_name=record_name, extension=extension,
                            sample=sample, symbol=symbol, subtype=subtype,
                            chan=chan, num=num, aux_note=aux_note,
                            label_store=label_store, fs=fs,
                            custom_labels=custom_labels)

    # Find out which input field describes the labels
    if symbol is None:
        if label_store is None:
            raise Exception("Either the 'symbol' field or the 'label_store' field must be set")
    else:
        if label_store is None:
            annotation.sym_to_aux()
        else:
            raise Exception("Only one of the 'symbol' and 'label_store' fields may be input, for describing annotation labels")

    # Perform field checks and write the annotation file
    annotation.wrann(write_fs=True, write_dir=write_dir)


def show_ann_labels():
    """
    Display the standard WFDB annotation label defintion map.

    When writing WFDB annotation files, please adhere to these standards
    for all annotation definitions present in this table, and define the
    `custom_labels` field for items that are not present.

    Columns
    -------
    label_store :
        The integer values used to store the labels in the file.
    symbol :
        The symbol used to display each label.
    description :
        The full description of what each label means.

    Examples
    --------
    >>> show_ann_labels()

    """
    print(ANN_LABELS)


def show_ann_extensions():
    """
    Display the standard WFDB annotation file extensions and their
    meanings.

    When writing WFDB annotation files, please adhere to these
    standards.

    Columns
    -------
    extension :
        The file extension.
    description :
        The description of the annotation content.
    human_reviewed :
        Whether the annotations were reviewed by humans.

    Examples
    --------
    >>> show_ann_extensions()

    """
    print(ANN_EXTENSIONS)


def rdann(record_name, extension, sampfrom=0, sampto=None,
          shift_samps=False, pb_dir=None, data_fields=None):
    """
    Read a WFDB annotation file named: <record_name>.<extension> and
    return the information of the annotation set.

    Parameters
    ----------
    record_name : str
        The record name of the WFDB annotation file. ie. for file
        '100.atr', record_name='100'.
    extension : str
        The annotatator extension of the annotation file. ie. for file
        '100.atr', extension='atr'.
    sampfrom : int, optional
        The minimum sample number for annotations to be returned.
    sampto : int, optional
        The maximum sample number for annotations to be returned.
    shift_samps : bool, optional
        Specifies whether to return the sample indices relative to
        `sampfrom` (True), or sample 0 (False).
    pb_dir : str, optional
        Option used to stream data from Physiobank. The Physiobank database
        directory from which to find the required annotation file. eg. For
        record '100' in 'http://physionet.org/physiobank/database/mitdb':
        pb_dir='mitdb'.
    data_fields : list, optional
        The data elements that are to be returned. Must be a subset of
        ANN_DATA_FIELDS.

    Returns
    -------
    annotation : wfdb Annotation
        The Annotation object. Call help(wfdb.Annotation) for the
        attribute descriptions.

    Notes
    -----
    For every annotation sample, the annotation file explictly stores
    the 'sample' and 'symbol' fields, but not necessarily the others.
    When reading annotation files using this function, fields which are
    not stored in the file will either take their default values of 0 or
    empty, or will be carried over from their previous values if any.

    Examples
    --------
    >>> ann = wfdb.rdann('sample-data/100', 'atr', sampto=300000)

    """

    data_fields = check_read_inputs(sampfrom, sampto, data_fields)

    # Read the file in byte pairs
    file_bytes = load_byte_pairs(record_name, extension, pb_dir)

    # Get the annotation data fields from the file bytes
    (sample, label_store, subtype, chan, num, aux_note) = extract_ann_data(
        file_bytes, sampto)

    # Get the indices of annotations that hold definition information
    # about the entire annotation file, and other empty annotations to
    # be removed.
    potential_info_inds, rm_inds = get_info_inds(sample, label_store, aux_note)

    # Try to extract information describing the annotation file
    (fs, custom_labels) = extract_ann_info(potential_info_inds, aux_note)

    # Remove annotations that do not store actual sample and label information
    (sample, label_store, subtype, chan, num, aux_note) = rm_empty_indices(
        rm_inds, sample, label_store, subtype, chan, num, aux_note)

    # Convert lists to numpy arrays
    (sample, label_store, subtype, chan, num) = lists_to_arrays(
        ['int', 'int', 'int', 'int', 'int', 'object'], sample, label_store,
        subtype, chan, num, aux_note)

    # Try to get fs from the header file if it is not contained in the
    # annotation file
    if fs is None:
        try:
            rec = record.rdheader(record_name, pb_dir)
            fs = rec.fs
        except:
            pass

    # Create the annotation object
    annotation = Annotation(record_name=os.path.split(record_name)[1],
                            extension=extension, sample=sample,
                            label_store=label_store, subtype=subtype,
                            chan=chan, num=num, aux_note=aux_note, fs=fs,
                            custom_labels=custom_labels)

    # Apply the desired index range
    if sampfrom or sampto:
        annotation.apply_range(sampfrom=sampfrom, sampto=sampto)

    # If specified, obtain annotation samples relative to the starting
    # index
    if shift_samps and len(sample) > 0 and sampfrom:
        annotation.sample = annotation.sample - sampfrom

    # Set the desired annotation data fields and remove the rest
    annotation._set_data_fields(data_fields=data_fields)

    return annotation


def rdanndata(record_name, extension, sampfrom=0, sampto=None,
              shift_samps=False, pb_dir=None, data_fields=None):
    """
    Read a WFDB annotation file named: <record_name>.<extension> and
    return the information of the annotation set.

    Parameters
    ----------
    record_name : str
        The record name of the WFDB annotation file. ie. for file
        '100.atr', record_name='100'.
    extension : str
        The annotatator extension of the annotation file. ie. for file
        '100.atr', extension='atr'.
    sampfrom : int, optional
        The minimum sample number for annotations to be returned.
    sampto : int, optional
        The maximum sample number for annotations to be returned.
    shift_samps : bool, optional
        Specifies whether to return the sample indices relative to
        `sampfrom` (True), or sample 0 (False).
    pb_dir : str, optional
        Option used to stream data from Physiobank. The Physiobank database
        directory from which to find the required annotation file. eg. For
        record '100' in 'http://physionet.org/physiobank/database/mitdb':
        pb_dir='mitdb'.
    data_fields : list, optional
        The data elements that are to be returned. Must be a subset of
        ANN_DATA_FIELDS.

    Returns
    -------
    data : Pandas DataFrame
        A dataframe containing the annotation data. Call
        `help(wfdb.Annotation)` for the attribute descriptions.

    fields : Dict, optional
        A dictionary


    Notes
    -----
    This function is a simplified wrapper around rdann

    Examples
    --------
    >>> ann = wfdb.rdann('sample-data/100', 'atr', sampto=300000)

    """
    annotation = rdann(record_name=record_name, extension=extension,
        sampfrom=sampfrom, sampto=sampto, shift_samps=shift_samps,
        pb_dir=pb_dir, data_fields=data_fields)

    fields = {'fs':annotation.fs}
    data = annotation.to_df()

    return data, fields

def check_read_inputs(sampfrom, sampto, data_fields):
    """
    Helper function to check the validity of input fields for `rdann`
    """
    if sampto and sampto <= sampfrom:
        raise ValueError('sampto must be greater than sampfrom')
    if sampfrom < 0:
        raise ValueError('sampfrom must be a non-negative integer')

    if isinstance(data_fields, str):
        data_fields = [data_fields]

    data_fields = data_fields or ANN_DATA_FIELDS[:6]

    if not data_fields.issubset(ANN_DATA_FIELDS):
        raise ValueError('elements of `data_fields` must only include the following:', ANN_DATA_FIELDS)

    return data_fields

def load_byte_pairs(record_name, extension, pb_dir):
    """
    Load the annotation file bytes as unsigned 8 bit values and arrange
    them into pairs

    """
    # local file
    if pb_dir is None:
        with open(record_name + '.' + extension, 'rb') as f:
            file_bytes = np.fromfile(f, '<u1').reshape([-1, 2])
    # physiobank file
    else:
        file_bytes = download._stream_annotation(
            '.'.join(record_nam, extension), pb_dir).reshape([-1, 2])

    return file_bytes


def extract_ann_data(file_bytes, sampto):
    """
    Extract the annotation data fields from the annotation file bytes
    """

    # Base annotation fields
    sample, label_store, subtype, chan, num, aux_note = [], [], [], [], [], []

    # Indexing Variables

    # Total number of sample from beginning of record. Annotation bytes
    # only store sample_diff
    sample_total = 0
    # Byte pair index
    bpi = 0

    # Process annotations. Iterate across byte pairs.
    # Sequence for one ann is:
    # - SKIP pair (if any)
    # - samp + sym pair
    # - other pairs (if any)
    # The last byte pair of the file is 0 indicating eof.
    while (bpi < file_bytes.shape[0] - 1):
        # Get the sample and label_store fields of the current annotation
        sample_diff, current_label_store, bpi = proc_core_fields(file_bytes, bpi)
        sample_total = sample_total + sample_diff
        sample.append(sample_total)
        label_store.append(current_label_store)

        # Process any other fields belonging to this annotation

        # Flags that specify whether the extra fields need to be updated
        update = {'subtype':True, 'chan':True, 'num':True, 'aux_note':True}
        # Get the next label store value - it may indicate additional
        # fields for this annotation, or the values of the next annotation.
        current_label_store = file_bytes[bpi, 1] >> 2

        while (current_label_store > 59):
            update, bpi = proc_extra_field(current_label_store, file_bytes, bpi,
                subtype, chan, num, aux_note, update)
            current_label_store = file_bytes[bpi, 1] >> 2

        # Set defaults or carry over previous values if necessary
        update_extra_fields(subtype, chan, num, aux_note, update)

        if sampto and sampto < sample_total:
            rm_last(sample, label_store, subtype, chan, num, aux_note)
            break

    return sample, label_store, subtype, chan, num, aux_note

def proc_core_fields(file_bytes, bpi):
    """
    Process file bytes to get the sample difference and label_store
    fields of the current annotation. Helper function to
    `extract_ann_data.
    """
    label_store = file_bytes[bpi, 1] >> 2

    # The current byte pair will contain either the actual d_sample + annotation store value,
    # or 0 + SKIP.

    # Not a skip - it is the actual sample number + annotation type store value
    if label_store != 59:
        sample_diff = file_bytes[bpi, 0] + 256 * (file_bytes[bpi, 1] & 3)
        bpi = bpi + 1
    # Skip. Note: Could there be another skip after the first?
    else:
        # 4 bytes storing dt
        sample_diff = 65536 * file_bytes[bpi + 1,0] + 16777216 * file_bytes[bpi + 1,1] \
             + file_bytes[bpi + 2,0] + 256 * file_bytes[bpi + 2,1]

        # Data type is long integer (stored in two's complement). Range -2**31 to 2**31 - 1
        if sample_diff > 2147483647:
            sample_diff = sample_diff - 4294967296

        # After the 4 bytes, the next pair's samp is also added
        sample_diff = sample_diff + file_bytes[bpi + 3, 0] + 256 * (file_bytes[bpi + 3, 1] & 3)

        # The label is stored after the 4 bytes. Samples here should be 0.
        label_store = file_bytes[bpi + 3, 1] >> 2
        bpi = bpi + 4

    return sample_diff, label_store, bpi

def proc_extra_field(label_store, file_bytes, bpi, subtype, chan, num,
                     aux_note, update):
    """
    Process extra fields belonging to the current annotation.
    Potential updated fields: subtype, chan, num, aux_note

    Helper function to `extract_ann_data`

    """
    # aux_note and sub are reset between annotations. chan and num copy over
    # previous value if missing.

    # SUB
    if label_store == 61:
        # sub is interpreted as signed char.
        subtype.append(file_bytes[bpi, 0].astype('i1'))
        update['subtype'] = False
        bpi = bpi + 1
    # CHAN
    elif label_store == 62:
        # chan is interpreted as un_signed char
        chan.append(file_bytes[bpi, 0])
        update['chan'] = False
        bpi = bpi + 1
    # NUM
    elif label_store == 60:
        # num is interpreted as signed char
        num.append(file_bytes[bpi, 0].astype('i1'))
        update['num'] = False
        bpi = bpi + 1
    # aux_note
    elif label_store == 63:
        # length of aux_note string. Max 256? No need to check other bits of
        # second byte?
        aux_notelen = file_bytes[bpi, 0]
        aux_notebytes = file_bytes[bpi + 1:bpi + 1 + int(np.ceil(aux_notelen / 2.)),:].flatten()
        if aux_notelen & 1:
            aux_notebytes = aux_notebytes[:-1]
        # The aux_note string
        aux_note.append(''.join([chr(char) for char in aux_notebytes]))
        update['aux_note'] = False
        bpi = bpi + 1 + int(np.ceil(aux_notelen / 2.))

    return update, bpi


def update_extra_fields(subtype, chan, num, aux_note, update):
    """
    Update the field if the current annotation did not
    provide a value.

    - aux_note and sub are set to default values if missing.
    - chan and num copy over previous value if missing.
    """

    if update['subtype']:
        subtype.append(0)

    if update['chan']:
        if chan == []:
            chan.append(0)
        else:
            chan.append(chan[-1])
    if update['num']:
        if num == []:
            num.append(0)
        else:
            num.append(num[-1])

    if update['aux_note']:
        aux_note.append('')


rx_fs = re.compile("## time resolution: (?P<fs>\d+\.?\d*)")
rx_custom_label = re.compile("(?P<label_store>\d+) (?P<symbol>\S+) (?P<description>.+)")


def get_info_inds(sample, label_store, aux_note):
    """
    Get the indices of annotations that potentially hold definition
    information about the entire annotation file, and other empty
    annotations to be removed.

    Note: There is no need to deal with SKIP annotations (label_store=59)
          which were already dealt with in proc_core_fields and hence
          not included here.
    """

    s0_inds = np.where(sample == np.int64(0))[0]
    note_inds = np.where(label_store == np.int64(22))[0]

    # sample = 0 with aux_note means there should be an fs or custom
    # label definition. Either way, they are to be removed.
    potential_info_inds = set(s0_inds).intersection(note_inds)

    # Other indices which are not actual annotations.
    notann_inds = np.where(label_store == np.int64(0))[0]

    rm_inds = potential_info_inds.union(set(notann_inds))

    return potential_info_inds, rm_inds


def extract_ann_info(potential_info_inds, aux_note):
    """
    Try to extract annotation definition information from annotation notes.
    Information that may be contained:
    - fs - sample=0, label_state=22, aux_note='## time resolution: XXX'
    - custom annotation label definitions
    """

    fs = None
    custom_labels = []

    if len(potential_info_inds) > 0:
        i = 0
        while i<len(potential_info_inds):
            if aux_note[i].startswith('## '):
                if not fs:
                    search_fs = rx_fs.findall(aux_note[i])
                    if search_fs:
                        fs = float(search_fs[0])
                        if round(fs, 8) == float(int(fs)):
                            fs = int(fs)
                        i += 1
                        continue
                if aux_note[i] == '## annotation type definitions':
                    i += 1
                    while aux_note[i] != '## end of definitions':
                        label_store, symbol, description = rx_custom_label.findall(aux_note[i])[0]
                        custom_labels.append((int(label_store), symbol, description))
                        i += 1
                    i += 1
            else:
                i += 1

    if not custom_labels:
        custom_labels = None

    return fs, custom_labels

def rm_empty_indices(*args):
    """
    Remove unwanted list indices. First argument is the list
    of indices to remove. Other elements are the lists
    to trim.
    """
    rm_inds = args[0]

    if not rm_inds:
        return args[1:]

    keep_inds = [i for i in range(len(args[1])) if i not in rm_inds]

    return [[a[i] for i in keep_inds] for a in args[1:]]

def lists_to_arrays(dtypes, *args):
    """
    Convert lists to numpy arrays. `dtypes` is a list of string dtypes.
    """
    return_args = []
    for i in range(len(dtypes)):
        return_args.append(np.array(args[i], dtype=dtypes[i]))
    return return_args

def rm_last(*args):
    """
    Pop each list
    """
    for a in args:
        a.pop()

def get_undefined_label_stores():
    """
    Get the label_store values in the allowed range that are not defined
    in the standard WFDB label map.
    """
    return list(set(range(50)) - set(ANN_LABELS['label_store']))
