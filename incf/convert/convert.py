import csv
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

import pandas as pd
import panel as pn

import incf.preprocess.simulations_h5 as h5
import incf.preprocess.simulations_matlab as mat
import incf.preprocess.structure as struct
import incf.preprocess.weights_distances as wdc
import incf.templates.templates as temp
import incf.utils as utils
from incf.convert.utils import Files

sys.path.append('..')
SID = None
DURATION = 3000
TRAVERSE_FOLDERS = True

OUTPUT = '../output'
DESC = 'default'
CENTERS = False

DEFAULT_TMPL, COORD_TMPL = 'sub-{}_desc-{}_{}.', 'desc-{}_{}.{}'


def check_compatibility(files):
    return len(set(files)) == len(files)


def check_input(path, files):
    all_files = []

    for file in files:
        fpath = os.path.join(path, file)

        if os.path.isdir(fpath) and TRAVERSE_FOLDERS:
            files = traverse_files(fpath, basename=True)
            all_files += files

    pn.state.notifications.success('Processing input data...', duration=DURATION)
    return 'success', files


def traverse_files(path: str, basename: bool = False) -> list:
    """
    Recursively traverse a specified folder and sub-folders. If `basename` is enabled,
    save only the file names. Otherwise, save absolute paths.

    :param path: str
        Path to the folder location to traverse.
    :param basename: bool
        Whether to save values by their absolute paths (False) or basename (True).
    :return: list
        Returns a list of basename or absolute paths.
    """

    contents = []

    for root, _, files in os.walk(path, topdown=True):
        for file in files:
            if basename:
                contents.append(get_filename(file))
            else:
                contents.append(os.path.join(root, file))

    return contents


def check_file(path, files, save=False):
    # subs = prepare_subs(get_content(path, files))
    subs = Files(path, files).subs
    print(subs)

    if save:
        save_output(subs, OUTPUT)

    return struct.create_layout(subs, OUTPUT)


def get_content(path, files):
    all_files = []

    for file in files:
        if os.path.isdir(os.path.join(path, file)):
            all_files += traverse_files(os.path.join(path, file))
        else:
            all_files.append(os.path.join(path, file))
    return all_files


def prepare_subs(file_paths, sid):
    global CENTERS

    subs = {}
    for file_path in file_paths:
        name = get_filename(file_path)
        desc = DESC + 'h5' if file_path.endswith('h5') else DESC

        subs[name] = {
            'fname': name,
            'sid': sid,
            'sep': find_separator(file_path),
            'desc': desc,
            'path': file_path,
            'ext': get_file_ext(file_path),
            'name': name.split('.')[0]
        }

        if subs[name]['name'] in ['tract_lengths', 'tract_length']:
            subs[name]['name'] = 'distances'

    return subs


def get_filename(path):
    return os.path.basename(path)


def get_file_ext(path):
    return path.split('.')[-1]


def find_separator(path):
    """
    Find the separator/delimiter used in the file to ensure no exception
    is raised while reading files.

    :param path:
    :return:
    """
    if path.endswith('.mat') or path.endswith('.h5'):
        return

    sniffer = csv.Sniffer()

    with open(path) as fp:
        try:
            delimiter = sniffer.sniff(fp.read(5000)).delimiter
        except Exception:
            delimiter = sniffer.sniff(fp.read(100)).delimiter

    delimiter = '\s' if delimiter == ' ' else delimiter
    return delimiter


def save_output(subs, output):
    # verify there are no conflicting folders
    conflict = len(os.listdir(output)) > 0

    def save(sub):
        for k, v in sub.items():
            if k in ['weights.txt', 'distances.txt', 'tract_lengths.txt']:
                wdc.save(sub[k], output)
            elif k in ['centres.txt']:
                wdc.save(sub[k], output, center=True)
            elif k.endswith('.mat'):
                mat.save(sub[k], output)
            elif k.endswith('.h5'):
                h5.save(sub[k], output)

    # overwrite existing content
    if conflict:
        pn.state.notifications.info('Output folder contains files. Removing them...', duration=DURATION)
        utils.rm_tree(output)

    # verify folders exist
    struct.check_folders(output)

    # save output files
    for k, v in subs.items():
        save(v)


def create_sub_struct(path, subs):
    sub = os.path.join(path, f"sub-{subs['sid']}")
    net = os.path.join(sub, 'net')
    spatial = os.path.join(sub, 'spatial')
    ts = os.path.join(sub, 'ts')

    for folder in [sub, net, spatial, ts]:
        if not os.path.exists(folder):
            print(f'Creating folder `{folder}`')
            os.mkdir(folder)

    return sub, net, spatial, ts


def get_shape(file, sep):
    return pd.read_csv(file, sep=sep, index_col=None, header=None).shape


def to_tsv(path, file=None):
    if file is None:
        Path(path).touch()
    else:
        params = {'sep': '\t', 'header': None, 'index': None}
        pd.DataFrame(file).to_csv(path, **params)


def to_json(path, shape, desc, ftype, coords=None):
    json_file = None

    if ftype == 'simulations':
        json_file = temp.merge_dicts(temp.JSON_template, temp.JSON_simulations)
    elif ftype == 'centers':
        json_file = temp.JSON_centers
    elif ftype == 'wd':
        json_file = temp.JSON_template

    if json_file is not None:
        with open(path, 'w') as f:
            json.dump(temp.populate_dict(json_file, shape=shape, desc=desc, coords=coords), f)
