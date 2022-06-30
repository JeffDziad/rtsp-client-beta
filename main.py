import errno
import math
import os
import cv2
import schedule
import datetime

# colored console output
from colorama import init, Fore, Style

init()

os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp'
cams = []
cycle_start = datetime.datetime.now()
Recorded_Days = 10
Recording_Length = 1


def cout(header, h_color, msg, m_color):
    print(('[' + h_color + '{h}' + Style.RESET_ALL + '] ' + m_color + '{m}' + Style.RESET_ALL).format(h=header, m=msg))


def get_resized_frame(frame, w, h):
    try:
        return cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
    except:
        cout('Frame Resizer', Fore.YELLOW, 'Failed resolution resize ({w}x{h}): {f})'.format(w=w, h=h, f=frame),
             Fore.BLUE)


def check_save_path(path):
    # check if path exists, if not, create it
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


class DataPoint:
    def __init__(self, title, value):
        self._title = title
        self._value = value

    def render_point(self, frame, x, y):
        cv2.putText(frame, text=self._title + ' : ' + str(self._value),
                    org=(x, y),
                    fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                    fontScale=0.5,
                    color=(255, 255, 255),
                    thickness=1,
                    lineType=cv2.LINE_AA)


class DataSheet:
    def __init__(self, origin_x, origin_y, width, height, color_tuple):
        self._origin = (origin_x, origin_y)
        self._color = color_tuple
        self._w = width
        self._h = height
        self._data_points = []
        self.VERT_PADDING = 20
        self.HOR_PADDING = 5

    def queue_point(self, data_point):
        self._data_points.append(data_point)

    def render_points(self, frame):
        self._h = (len(self._data_points) * self.VERT_PADDING) + 10

        points_rendered = 0
        cv2.rectangle(frame, (self._origin[0], self._origin[1]), (self._origin[0] + self._w, self._origin[1] + self._h),
                      self._color, -1)

        for dp in self._data_points:
            points_rendered += 1
            dp.render_point(frame, self._origin[0] + self.HOR_PADDING, self._origin[1] + (points_rendered * self.VERT_PADDING))

        self._data_points = []


class Cam:
    def __init__(self, url, cam_name):
        self._background = False
        self._isSaving = True
        self._isActive = True
        self._isLinux = True

        self._url = url
        self._cam_name = cam_name
        self._root_fldr = 'recordings/{name}/'.format(name=self._cam_name)
        self._destination = self._root_fldr
        self._datasheet = DataSheet(10, 10, 200, 200, (255, 0, 0))

        self._cap = None
        self.gen_capture()

        self._frame_width = int(self._cap.get(3))
        self._frame_height = int(self._cap.get(4))
        self._save_length = Recording_Length
        self._title = str(datetime.datetime.now())
        self._files_saved = 0
        self._frames_captured = 0

        self._saver = None
        init_time = datetime.datetime.now()
        self.gen_saver(str(init_time), self.format_destination_path(init_time))

        # register new file event
        schedule.every(self._save_length).minutes.do(self.new_file)

    def gen_capture(self):
        self._cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)

    def gen_saver(self, title, destination):
        cout('Saver - {c}'.format(c=self._cam_name), Fore.GREEN,
             'New recording cycle started. ({t}, {d})'.format(t=title, d=destination), Fore.BLUE)
        check_save_path(destination)
        if self._isLinux:
            dest = destination + '{title}.avi'.format(title=title.replace(':', '_'))
            self._saver = cv2.VideoWriter(dest, cv2.VideoWriter_fourcc('m', 'p', '4', 'v'), 20,
                                          (self._frame_width, self._frame_height))
        else:
            dest = destination + '{title}.avi'.format(title=title.replace(':', '_'))
            self._saver = cv2.VideoWriter(dest, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'), 20,
                                          (self._frame_width, self._frame_height))

    def stop(self):
        self._isSaving = False
        self._saver.release()
        self._cap.release()
        self._isActive = False

    def new_file(self):
        self._files_saved += 1
        cout('Saver - {c}'.format(c=self._cam_name), Fore.RED, 'Recording cycle ended. File Saved', Fore.BLUE)
        self.stop_saving()
        start_time = datetime.datetime.now()
        # update destination
        self._destination = self.format_destination_path(start_time)
        # assign new title
        self._title = str(start_time)
        self.start_saving()

    def format_destination_path(self, dt):
        return 'recordings/{name}/'.format(name=self._cam_name) + '{year}/'.format(
            year=str(dt.year)) + '{month}/'.format(month=str(dt.month)) + '{day}/'.format(day=str(dt.day))

    def start_saving(self):
        # regenerate saver with new title and destination
        self._isSaving = True
        self.gen_saver(self._title, self._destination)

    def stop_saving(self):
        # close saver instance
        self._isSaving = False
        self._saver.release()

    def update(self):
        if self._isActive:
            if not self._cap.isOpened():
                print("Oops, there was a problem connecting to {link}".format(link=self._url))
            else:
                success, frame = self._cap.read()
                self._frames_captured += 1
                # if background is false, display live stream
                if not self._background:
                    self.display(frame)
                if self._isSaving:
                    self.write_frame(frame)

    def render_frame_text(self, frame):
        self._datasheet.queue_point(DataPoint('Files Saved', self._files_saved))
        self._datasheet.render_points(frame)
        return frame

    def write_frame(self, frame):
        # determine if it's time to create a new file or delete old files
        self._saver.write(frame)

    def display(self, frame):
        resize_w = 854
        resize_h = 480
        if not self._background:
            resized = get_resized_frame(frame, resize_w, resize_h)
            resized = self.render_frame_text(resized)
            if self._isSaving:
                if math.sin(self._frames_captured * 0.2) > 0:
                    cv2.circle(resized, (resize_w - 40, 35), 20, (0, 0, 255), -1)
            else:
                rect_size = 50
                cv2.rectangle(resized, (resize_w - rect_size - 10, rect_size + 10), (resize_w - 10, rect_size + 10),
                              (255, 0, 0), -1)
            cv2.imshow(self._cam_name, resized)


def clear_old_videos():
    thresh = datetime.datetime.now() + datetime.timedelta(-Recorded_Days)
    cout('File Clearing', Fore.YELLOW, 'Removing files older than ' + str(thresh), Fore.BLUE)
    files = []
    root = 'recordings'
    for cam_fldr in os.listdir(root):
        for year_fldr in os.listdir(root + '/' + cam_fldr):
            for month_fldr in os.listdir(root + '/' + cam_fldr + '/' + year_fldr):
                for day_fldr in os.listdir(root + '/' + cam_fldr + '/' + year_fldr + '/' + month_fldr):
                    for rec_file in os.listdir(
                            root + '/' + cam_fldr + '/' + year_fldr + '/' + month_fldr + '/' + day_fldr):
                        rec_path = '{r}/{c}/{y}/{m}/{d}/{rf}'.format(r=root, c=cam_fldr, y=year_fldr, m=month_fldr,
                                                                     d=day_fldr, rf=rec_file)
                        rec_date = rec_file.split('.')[0]
                        rec_date = rec_date.replace('_', ':')
                        files.append((datetime.datetime.strptime(rec_date, '%Y-%m-%d %H:%M:%S'), rec_path))
    for rec in files:
        if rec[0] < thresh:
            cout('File Clearing', Fore.YELLOW, 'Removing File: ' + rec[1], Fore.BLUE)
            os.remove(rec[1])
        else:
            cout('File Clearing', Fore.YELLOW, 'Keeping File: ' + rec[1], Fore.GREEN)


cams.append(Cam('rtsp://beverly1:0FtYard1@192.168.1.245/live', 'Beverly_Front'))


# cams.append(Cam('rtsp://admin:jeffjadd@192.168.1.246/live', 'Beverly_Backyard'))


def main():
    schedule.every().day.at('23:55').do(clear_old_videos)

    # program loop
    while True:

        for c1 in cams:
            c1.update()

        schedule.run_pending()

        if cv2.waitKey(1) == 27:
            for c2 in cams:
                c2.stop()
            break


if __name__ == "__main__":
    main()
