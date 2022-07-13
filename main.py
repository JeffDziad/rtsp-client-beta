import errno
import math
import os
import cv2
import schedule
import datetime
import numpy as np
import utils


os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp'
cams = []
cycle_start = datetime.datetime.now()
Recorded_Days = 2  # days
Recording_Length = 10  # minutes


def get_resized_frame(frame, w, h):
    try:
        return cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
    except:
        utils.cout('Frame Resizer', utils.Fore.YELLOW,
                   'Failed resolution resize ({w}x{h}): {f})'.format(w=w, h=h, f=frame),
                   utils.Fore.BLUE)


def check_save_path(path):
    # check if path exists, if not, create it
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


class SecurityAgent:
    def __init__(self):
        self.running = True


class DataPoint:
    title = ""
    value = None

    def __init__(self, title, value, color=(0, 0, 0)):
        self.title = title
        self.value = value
        self.font = cv2.FONT_HERSHEY_DUPLEX
        self.font_scale = 0.5
        self.color = color
        self.thickness = 1
        self.line_type = cv2.LINE_AA
        self.text = self.title + ' : ' + str(self.value)

    def get_text_width(self):
        return cv2.getTextSize(self.text, self.font, self.font_scale, self.thickness)[0][0]

    def render_point(self, frame, x, y):
        cv2.putText(frame, text=self.text,
                    org=(x, y),
                    fontFace=self.font,
                    fontScale=self.font_scale,
                    color=self.color,
                    thickness=self.thickness,
                    lineType=self.line_type)


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

    def find_widest_prop(self):
        out = 0
        for prop in self._data_points:
            w = prop.get_text_width()
            if w > out:
                out = w
        return out

    def render_points(self, frame):
        # setup variables
        self._h = (len(self._data_points) * self.VERT_PADDING) + 10
        points_rendered = 0
        c_width = self.find_widest_prop()
        x, y, w, h = self._origin[0], self._origin[1], c_width + self.HOR_PADDING * 2, self._h

        # grab cropped section where box will be
        if frame is not None:
            sub_img = frame[y: y + h, x: x + w]
            # create a blue rect from sub_img properties
            blue_rect = np.ones(sub_img.shape, dtype=np.uint8) * 255
            # combine
            final_edit = cv2.addWeighted(sub_img, 0.5, blue_rect, 0.5, 1.0)
            # re-insert
            frame[y:y + h, x:x + w] = final_edit

            for dp in self._data_points:
                points_rendered += 1
                dp.render_point(frame, x + self.HOR_PADDING,
                                y + (points_rendered * self.VERT_PADDING))

        self._data_points = []
        return frame


class Cam:
    def __init__(self, url, cam_name):
        self.cam_name = cam_name

        self._background = False
        self._isSaving = True
        self._isActive = True
        self._isLinux = True

        self._resize_w = 854
        self._resize_h = 480
        self._url = url
        self._root_fldr = 'recordings/{name}/'.format(name=self.cam_name)
        self.destination = self._root_fldr
        self._datasheet = DataSheet(10, 10, 200, 200, (255, 0, 0))
        self._sessionsheet = DataSheet(10, self._resize_h - 80, 200, 200, (255, 0, 0))

        self._cap = None
        self.gen_capture()

        self._frame_width = int(self._cap.get(3))
        self._frame_height = int(self._cap.get(4))
        self._save_length = Recording_Length
        self._title = str(datetime.datetime.now())
        self.files_saved = 0
        self._frames_captured = 0

        self._saver = None
        self.init_time = datetime.datetime.now()
        self.gen_saver(str(self.init_time), self.format_destination_path(self.init_time))

        # register new file event
        schedule.every(self._save_length).minutes.do(self.new_file)

    def get_fps(self):
        now = datetime.datetime.now()
        diff = now - self.init_time
        return self._frames_captured / diff.total_seconds()

    def gen_capture(self):
        self._cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)

    def gen_saver(self, title, destination):
        utils.cout('Saver - {c}'.format(c=self.cam_name), utils.Fore.GREEN,
                   'New recording cycle started. ({t}, {d})'.format(t=title, d=destination), utils.Fore.BLUE)
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
        self.files_saved += 1
        utils.cout('Saver - {c}'.format(c=self.cam_name), utils.Fore.RED, 'Recording cycle ended. File Saved',
                   utils.Fore.BLUE)
        self.stop_saving()
        start_time = datetime.datetime.now()
        # update destination
        self.destination = self.format_destination_path(start_time)
        # assign new title
        self._title = str(start_time)
        self.start_saving()

    def format_destination_path(self, dt):
        return 'recordings/{name}/'.format(name=self.cam_name) + '{year}/'.format(
            year=str(dt.year)) + '{month}/'.format(month=str(dt.month)) + '{day}/'.format(day=str(dt.day))

    def start_saving(self):
        # regenerate saver with new title and destination
        self._isSaving = True
        self.gen_saver(self._title, self.destination)

    def stop_saving(self):
        # close saver instance
        self._isSaving = False
        self._saver.release()

    def update(self):
        if self._isActive:
            if not self._cap.isOpened():
                utils.cout("Cam - {c}".format(c=self.cam_name), utils.Fore.YELLOW,
                           "Oops, there was a problem connecting to {link}. Stopping process.".format(link=self._url),
                           utils.Fore.WHITE)
                self.stop()
            else:
                success, frame = self._cap.read()
                if success:
                    self._frames_captured += 1
                    # if background is false, display live stream
                    if not self._background:
                        self.display(frame)
                    if self._isSaving:
                        self.write_frame(frame)

    def render_frame_attributes(self, frame):
        self._datasheet.queue_point(DataPoint('Name', self.cam_name))
        self._datasheet.queue_point(DataPoint('Files Saved', self.files_saved))
        self._datasheet.queue_point(DataPoint('Recording Start', self._title))
        self._datasheet.queue_point(DataPoint('FPS', str(format(self.get_fps(), '.2f'))))
        fnl = self._datasheet.render_points(frame)
        self._sessionsheet.queue_point(DataPoint('Session Details', ""))
        self._sessionsheet.queue_point(DataPoint('Start', str(self.init_time)))
        self._sessionsheet.queue_point(DataPoint('Security Mode', "Enabled" if sa.running else "Disabled", (0, 255, 0) if sa.running else (0, 0, 255)))
        fnl = self._sessionsheet.render_points(fnl)
        return fnl

    def write_frame(self, frame):
        # determine if it's time to create a new file or delete old files
        self._saver.write(frame)

    def display_preprocess(self, frame):
        out = get_resized_frame(frame, self._resize_w, self._resize_h)
        # out = ObjectDetection.render_object_rects(out)
        out = self.render_frame_attributes(out)
        return out

    def display(self, frame):
        if not self._background:
            processed = self.display_preprocess(frame)
            if self._isSaving:
                if math.sin(self._frames_captured * 0.2) > 0:
                    cv2.circle(processed, (self._resize_w - 40, 35), 20, (0, 0, 255), -1)
            else:
                rect_size = 50
                cv2.rectangle(processed, (self._resize_w - rect_size - 10, rect_size + 10),
                              (self._resize_w - 10, rect_size + 10), (255, 0, 0), -1)
            cv2.imshow(self.cam_name, processed)


def clear_old_videos():
    thresh = datetime.datetime.now() + datetime.timedelta(-Recorded_Days)
    utils.cout('File Clearing', utils.Fore.YELLOW, 'Removing files older than ' + str(thresh), utils.Fore.BLUE)
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
            utils.cout('File Clearing', utils.Fore.YELLOW, 'Removing File: ' + rec[1], utils.Fore.BLUE)
            os.remove(rec[1])
        else:
            utils.cout('File Clearing', utils.Fore.YELLOW, 'Keeping File: ' + rec[1], utils.Fore.GREEN)

sa = SecurityAgent()
cams.append(Cam('rtsp://beverly1:0FtYard1@192.168.1.245/live', 'Beverly_Front'))
# cams.append(Cam('rtsp://admin:jeffjadd@192.168.1.246/live', 'Beverly_Backyard'))


def export_cam_json():
    for cam in cams:
        to_be_saved = {
            "cam_name": cam.cam_name,
            "session_start": str(cam.init_time),
            "session_saves": cam.files_saved,
            "current_save_path": cam.destination
        }
        try:
            utils.write_json(to_be_saved, cam.cam_name)
            utils.cout("Exporter - json", utils.Fore.YELLOW,
                       "Updated file at path: {p}".format(p=utils.concat_path(cam.cam_name)),
                       utils.Fore.BLUE)
        except:
            utils.cout("Exporter - json", utils.Fore.YELLOW,
                       "Failed to write to path: {p}".format(p=utils.concat_path(cam.cam_name)),
                       utils.Fore.BLUE)


def main():
    # clear videos event
    schedule.every().day.at('23:55').do(clear_old_videos)
    # export cam data event
    schedule.every(30).seconds.do(export_cam_json)

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
