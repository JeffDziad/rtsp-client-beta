# colored console output
import json

from colorama import init, Fore, Style

init()

JSON_ROOT_PATH = 'cam_data/'

json_files = []


class JSONFile:
    def __init__(self, filename):
        self.filename = filename
        self.file = open(concat_path(filename), 'w+')


def concat_path(filename):
    return JSON_ROOT_PATH + filename + '.json'


def cout(header, h_color, msg, m_color):
    print(('[' + h_color + '{h}' + Style.RESET_ALL + '] ' + m_color + '{m}' + Style.RESET_ALL).format(h=header, m=msg))


def finalize_json_write(stream, data):
    stream.seek(0)
    stream.write(json.dumps(data) + " ")
    stream.truncate()


def write_json(python_obj, filename):
    match = False
    match_i = 0
    for j in json_files:
        if j.filename == filename:
            match = True
            break
        match_i += 1
    if match:
        finalize_json_write(json_files[match_i].file, python_obj)
    else:
        next_i = len(json_files)
        json_files.append(JSONFile(filename))
        finalize_json_write(json_files[next_i].file, python_obj)
