# colored console output
import json

from colorama import init, Fore, Style

init()

JSON_ROOT_PATH = 'cam_data/'


def concat_path(filename):
    return JSON_ROOT_PATH + filename + '.json'


def cout(header, h_color, msg, m_color):
    print(('[' + h_color + '{h}' + Style.RESET_ALL + '] ' + m_color + '{m}' + Style.RESET_ALL).format(h=header, m=msg))


def write_json(python_obj, filename):
    json_file = open(concat_path(filename), 'w+')
    json_file.seek(0)
    json_file.write(json.dumps(python_obj) + " ")
    json_file.truncate()
    json_file.close()
