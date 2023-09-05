import base64
import hashlib
import json
import logging
import random
import threading
import time
import requests
from pyDes import des, PAD_PKCS5, CBC
from apscheduler.schedulers.blocking import BlockingScheduler
import gc


class YunRun:
    __school_id = '127'
    __school_host = 'http://47.99.163.239:8080'
    __app_edition = '2.3.1'
    __system_edition = '12'
    __map_key = ''
    __cipher = 'YUNZHIEE'
    __initialization_vector = '\1\2\3\4\5\6\7\x08'

    __allow_overflow_distance = 0.1
    __single_mileage_min_offset = 2
    __single_mileage_max_offset = -2

    __split_count = 10

    def __init__(self, user_name, user_password):
        try:
            self.__logger = logging.getLogger(user_name)
            self.__logger.setLevel(logging.INFO)

            file_handler = logging.FileHandler('yunrun.log')
            file_handler.setLevel(logging.INFO)

            formatter = logging.Formatter('%(asctime)s - %(name)s - %(funcName)s - %(message)s')
            file_handler.setFormatter(formatter)

            self.__logger.addHandler(file_handler)

            self.__user_name = user_name
            self.__user_password = user_password

            self.__device_name = self.__get_device_name()
            self.__device_id = self.__get_device_id()

            self.__user_token = ''
            self.__now_distance = 0
            self.__now_time = 0
            self.__manage_list = []

        except Exception as e:
            self.__logger.error(f'发生了错误：{e}', exc_info=True)

    def run(self):
        try:
            self.__prepare_run()
            self.__start_run()
            self.__running()
            self.__finish_run()
            self.__sign_out()
        except Exception as e:
            self.__logger.error(f'发生了错误：{e}', exc_info=True)

    def __prepare_run(self):
        self.__user_token = self.__sign_in()
        self.__get_run_info()

        i = 0
        while (self.__now_distance / 1000 > getattr(self,
                                                    'raSingleMileageMin') + YunRun.__allow_overflow_distance) or self.__now_distance == 0:
            i += 1
            self.__logger.info('第' + str(i) + '次尝试...')
            self.__manage_list = []
            self.__now_distance = 0
            self.__now_time = 0
            self.__task_list = []
            self.__task_count = 0
            self.__myLikes = 0
            self.__generate_task(getattr(self, 'points'))
        self.__now_time = int(random.uniform(getattr(self, 'raPaceMin'), getattr(self, 'raPaceMax')) * 60 * (
                self.__now_distance / 1000))
        self.__logger.info(
            '打卡点标记完成！本次将打卡' + str(self.__myLikes) + '个点，处理' + str(len(self.__task_list)) + '个点，总计'
            + format(self.__now_distance / 1000, '.2f')
            + '公里，将耗时' + str(self.__now_time // 60) + '分' + str(self.__now_time % 60) + '秒')

    def __get_run_info(self):
        data = json.loads(self.__get_response("/run/getHomeRunInfo", ""))['data']['cralist'][0]

        self.__dict__.update({
            'raType': data['raType'],
            'raId': data['id'],
            'schoolId': data['schoolId'],
            'raRunArea': data['raRunArea'],
            'raDislikes': data['raDislikes'],
            'raMinDislikes': data['raDislikes'],
            'raSingleMileageMin': data['raSingleMileageMin'],
            'raSingleMileageMax': data['raSingleMileageMax'],
            'raCadenceMin': data['raCadenceMin'],
            'raCadenceMax': data['raCadenceMax'],
            'raPaceMin': data['raPaceMin'],
            'raPaceMax': data['raPaceMax'],
            'points': data['points'].split('|')
        })

    def __start_run(self) -> None:
        data = {
            'raRunArea': getattr(self, 'raRunArea'),
            'raType': getattr(self, 'raType'),
            'raId': getattr(self, 'raId')
        }
        j = json.loads(self.__get_response('/run/start', json.dumps(data)))
        if j['code'] == 200:
            self.__dict__.update({
                'recordStartTime': j['data']['recordStartTime'],
                'crsRunRecordId': j['data']['id'],
                'userName': j['data']['studentId'],
            })
            self.__logger.info("云运动任务创建成功！")

    def __split(self, points):
        data = {
            'cardPointList': points,
            'crsRunRecordId': getattr(self, 'recordStartTime'),
            'schoolId': YunRun.__school_id,
            'userName': self.__user_name
        }
        headers = {
            'Content-Type': 'text/plain;charset=utf-8',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'User-Agent': 'okhttp/3.12.0'
        }
        response = requests.post(url=f'{YunRun.__school_host}/run/splitPoints',
                                 data=YunRun.__des_encrypt(json.dumps(data)),
                                 headers=headers)
        self.__logger.info(f'{response}')

    def __running(self):
        sleep_time = self.__now_time / (self.__task_count + 1)
        self.__logger.info('等待' + format(sleep_time, '.2f') + '秒...')
        time.sleep(sleep_time)
        for task_index, task in enumerate(self.__task_list):
            self.__logger.info('开始处理第' + str(task_index + 1) + '个点...')
            for split_index, split in enumerate(task['points']):
                self.__split(split)
                self.__logger.info(
                    '  第' + str(split_index + 1) + '次splitPoint发送成功！等待' + format(sleep_time, '.2f') + '秒...')
                time.sleep(sleep_time)
            self.__logger.info('第' + str(task_index + 1) + '个点处理完毕！')

    def __generate_task(self, points):
        random_points = random.sample(points, getattr(self, 'raDislikes'))
        for point_index, point in enumerate(random_points):
            if self.__now_distance / 1000 < getattr(self, 'raSingleMileageMin') or self.__myLikes < getattr(self,
                                                                                                            'raMinDislikes'):
                self.__manage_list.append({
                    'point': point,
                    'marked': 'Y',
                    'index': point_index
                })
                self.__add_task(point)
                self.__myLikes += 1
            else:
                self.__manage_list.append({
                    'point': point,
                    'marked': 'N',
                    'index': ''
                })

        if self.__now_distance / 1000 < getattr(self, 'raSingleMileageMin'):
            self.__logger.info('公里数不足' + str(getattr(self, 'raSingleMileageMin')) + '公里，将自动回跑...')
            index = 0
            while self.__now_distance / 1000 < getattr(self, 'raSingleMileageMin'):
                self.__add_task(self.__manage_list[index]['point'])
                index = (index + 1) % getattr(self, 'raDislikes')

    def __add_task(self, point):
        if not self.__task_list:
            origin = YunRun.__get_start_point()
        else:
            origin = self.__task_list[-1]['originPoint']
        data = {
            'key': YunRun.__map_key,
            'origin': origin,
            'destination': point
        }
        response = requests.get("https://restapi.amap.com/v4/direction/bicycling", params=data)
        j = json.loads(response.text)
        split_points = []
        split_point = []
        for path in j['data']['paths']:
            self.__now_distance += path['distance']
            path['steps'][-1]['polyline'] += ';' + point
            for step in path['steps']:
                polyline = step['polyline']
                points = polyline.split(';')
                for p in points:
                    split_point.append({
                        'point': p,
                        'runStatus': '1',
                        'speed': format(
                            random.uniform(getattr(self, 'raSingleMileageMin'), getattr(self, 'raSingleMileageMax')),
                            '.2f'),
                        'isFence': 'Y'
                    })
                    if len(split_point) == YunRun.__split_count:
                        split_points.append(split_point)
                        self.__task_count = self.__task_count + 1
                        split_point = []

        if len(split_point) > 1:
            b = split_point[0]['point']
            for i in range(1, len(split_point)):
                new_split_point = []
                a = b
                b = split_point[i]['point']
                a_split = a.split(',')
                b_split = b.split(',')
                a_x = float(a_split[0])
                a_y = float(a_split[1])
                b_x = float(b_split[0])
                b_y = float(b_split[1])
                d_x = (b_x - a_x) / YunRun.__split_count
                d_y = (b_y - a_y) / YunRun.__split_count
                for j in range(0, YunRun.__split_count):
                    new_split_point.append({
                        'point': str(a_x + (j + 1) * d_x) + ',' + str(a_y + (j + 1) * d_y),
                        'runStatus': '1',
                        'speed': format(
                            random.uniform(getattr(self, 'raSingleMileageMin'), getattr(self, 'raSingleMileageMax')),
                            '.2f'),
                        'isFence': 'Y'
                    })
                split_points.append(new_split_point)
                self.__task_count = self.__task_count + 1
        elif len(split_point) == 1:
            split_points[-1][-1] = split_point[0]

        self.__task_list.append({
            'originPoint': point,
            'points': split_points
        })

    def __finish_run(self) -> None:
        self.__logger.info('发送结束信号...')
        data = {
            'recordMileage': format(self.__now_distance / 1000, '.2f'),
            'recodeCadence': self.__get_cadence(),
            'recodePace': format(self.__now_time / 60 / (self.__now_distance / 1000), '.2f'),
            'deviceName': self.__device_name,
            'sysEdition': YunRun.__system_edition,
            'appEdition': YunRun.__app_edition,
            'raIsStartPoint': 'Y',
            'raIsEndPoint': 'Y',
            'raRunArea': getattr(self, 'raRunArea'),
            'recodeDislikes': self.__myLikes,
            'raId': getattr(self, 'raId'),
            'raType': getattr(self, 'raType'),
            'id': getattr(self, 'crsRunRecordId'),
            'duration': self.__now_time,
            'recordStartTime': getattr(self, 'recordStartTime'),
            'manageList': self.__manage_list
        }
        response = self.__get_response("/run/finish", json.dumps(data))
        self.__logger.info(response)

    def __get_response(self, router: str, data: str) -> str:
        headers = {
            'token': self.__user_token,
            'isApp': 'app',
            'deviceId': self.__device_id,
            'version': YunRun.__app_edition,
            'platform': 'android',
            'Content-Type': 'text/plain; charset=utf-8',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'User-Agent': 'okhttp/3.12.0'
        }

        response = requests.post(url=f'{YunRun.__school_host}{router}', data=YunRun.__des_encrypt(data),
                                 headers=headers)
        return response.text

    def __sign_in(self) -> str:
        data = {
            'password': self.__user_password,
            'schoolId': YunRun.__school_id,
            'userName': self.__user_name,
            'type': '1'
        }
        headers = {
            'isApp': 'app',
            'deviceId': self.__get_device_id(),
            'version': YunRun.__app_edition,
            'platform': 'android',
            'Content-Type': 'text/plain; charset=utf-8',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'User-Agent': 'okhttp/3.12.0'
        }
        response = requests.post(url=f'{YunRun.__school_host}/login/appLogin',
                                 data=YunRun.__des_encrypt(json.dumps(data)),
                                 headers=headers)
        data = json.loads(response.text)

        if data['code'] == 200:
            self.__logger.info("登录成功")
            return data['data']['token']
        else:
            self.__logger.info(data['msg'])
            return ''

    def __sign_out(self):
        data = json.loads(self.__get_response("/login/signOut", ""))

        if data['code'] == 200:
            self.__logger.info("退出登录成功")

    def __get_cadence(self) -> str:
        shifting = int((getattr(self, 'raCadenceMax') - getattr(self, 'raCadenceMin')) / 10)
        max_value = getattr(self, 'raCadenceMax') - shifting
        min_value = getattr(self, 'raCadenceMin') + shifting
        hash_value = hashlib.sha256(self.__user_name.encode()).hexdigest()
        x = int(hash_value, 16) % 1000
        y = x / 1000 * (max_value - min_value) + min_value
        return str(int(max(min(y + random.randint(-shifting, shifting), max_value), min_value)))

    def __get_device_id(self, length: int = 16) -> str:
        combined_str = self.__user_name + self.__user_password
        hash_value = hashlib.sha256(combined_str.encode()).hexdigest()
        return str(int(hash_value, 16))[:length]

    @staticmethod
    def __des_encrypt(s: str, key: str = __cipher, iv: str = __initialization_vector) -> bytes:
        secret_key = key
        k = des(secret_key, CBC, iv, pad=None, padmode=PAD_PKCS5)
        en = k.encrypt(s, padmode=PAD_PKCS5)
        return base64.b64encode(en)

    @staticmethod
    def __des_decrypt(s: str, key: str = __cipher, iv: str = __initialization_vector) -> str:
        secret_key = key
        k = des(secret_key, CBC, iv, pad=None, padmode=PAD_PKCS5)
        de = k.decrypt(base64.b64decode(s), padmode=PAD_PKCS5)
        return de

    @staticmethod
    def __get_start_point() -> str:
        latitude = random.uniform(118.375059, 118.377209)
        longitude = random.uniform(31.279333, 31.287604)
        return f'{latitude},{longitude}'

    def __get_device_name(self) -> str:
        if int(self.__user_name) % 3 == 0:
            return 'Xiaomi(Mi10)'
        else:
            return 'Xiaomi'


def task():
    with open('users.json', 'r') as f:
        yunruns = [YunRun(user['user_name'], user['user_password']) for user in json.load(f)]

    threads = []
    for i, yunrun in enumerate(yunruns):
        thread = threading.Thread(target=yunrun.run)
        threads.append(thread)
        thread.start()
        if i < len(yunruns) - 1:
            time.sleep(60 * 100 / len(yunruns) + random.random(0, 1) * 2 - 1)

    for thread in threads:
        thread.join()

    gc.collect()


if __name__ == '__main__':
    scheduler = BlockingScheduler()
    scheduler.add_job(task, 'cron', hour=6, minute=1)
    scheduler.start()
