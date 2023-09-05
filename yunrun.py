import base64
import hashlib
import json
import logging
import random
import time
import requests
from pyDes import des, PAD_PKCS5, CBC
from colorama import init, Fore, Back, Style


class YunRun:
    __school_id = '127'
    __school_host = 'http://47.99.163.239:8080'
    __app_edition = '2.3.1'
    __system_edition = '12'
    __cipher = 'YUNZHIEE'
    __initialization_vector = '\1\2\3\4\5\6\7\x08'

    __allow_overflow_distance = 0.1
    __single_mileage_min_offset = 2
    __single_mileage_max_offset = -2

    __split_count = 10

    __point_shifting = 0.000008

    def __init__(self, user_name, user_password, map_key):
        try:
            self.__user_name = user_name
            self.__user_password = user_password

            self.__device_name = self.__get_device_name()
            self.__device_id = self.__get_device_id()

            self.__map_key = map_key

            self.__user_token = ''
            self.__now_distance = 0
            self.__now_time = 0
            self.__manage_list = []

        except Exception as e:
            print(f'发生了错误：{e}', exc_info=True)

    def run(self):
        try:
            self.__prepare_run()
            self.__start_run()
            self.__running()
            self.__finish_run()
            self.__sign_out()
        except Exception as e:
            print(f'发生了错误：{e}', exc_info=True)

    def __prepare_run(self):
        self.__user_token = self.__sign_in()
        self.__get_run_info()

        i = 0
        while (self.__now_distance / 1000 > getattr(self,
                                                    'raSingleMileageMin') + YunRun.__allow_overflow_distance) or self.__now_distance == 0:
            i += 1
            print('第' + str(i) + '次尝试...')
            self.__manage_list = []
            self.__now_distance = 0
            self.__now_time = 0
            self.__task_list = []
            self.__task_count = 0
            self.__myLikes = 0
            self.__generate_task(getattr(self, 'points'))
        self.__now_time = int(random.uniform(getattr(self, 'raPaceMin'), getattr(self, 'raPaceMax')) * 60 * (
                self.__now_distance / 1000))
        print(
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
            print("云运动任务创建成功！")

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
        print(f'{response}')

    def __running(self):
        sleep_time = self.__now_time / (self.__task_count + 1)
        print('等待' + format(sleep_time, '.2f') + '秒...')
        time.sleep(sleep_time)
        for task_index, task in enumerate(self.__task_list):
            print('开始处理第' + str(task_index + 1) + '个点...')
            for split_index, split in enumerate(task['points']):
                self.__split(split)
                print(
                    '  第' + str(split_index + 1) + '次splitPoint发送成功！等待' + format(sleep_time, '.2f') + '秒...')
                time.sleep(sleep_time)
            print('第' + str(task_index + 1) + '个点处理完毕！')

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
            print('公里数不足' + str(getattr(self, 'raSingleMileageMin')) + '公里，将自动回跑...')
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
            'key': self.__map_key,
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
                        'point': str(a_x + (
                                j + 1) * d_x + random.random() * YunRun.__point_shifting - YunRun.__point_shifting / 2) + ',' + str(
                            a_y + (
                                    j + 1) * d_y + random.random() * YunRun.__point_shifting - YunRun.__point_shifting / 2),
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
        print('发送结束信号...')
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
        print(response)

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
            print("登录成功")
            return data['data']['token']
        else:
            print(data['msg'])
            return ''

    def __sign_out(self):
        data = json.loads(self.__get_response("/login/signOut", ""))

        if data['code'] == 200:
            print("退出登录成功")

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


if __name__ == '__main__':
    try:
        logo = '''  
     _    _         _  ____                 _                          
    | |  | |       (_)|  _ \               | |                         
    | |__| |  __ _  _ | |_) |  ___    ___  | |      __ _  _ __    __ _ 
    |  __  | / _` || ||  _ <  / _ \  / _ \ | |     / _` || '_ \  / _` |
    | |  | || (_| || || |_) || (_) || (_) || |____| (_| || | | || (_| |
    |_|  |_| \__,_||_||____/  \___/  \___/ |______|\__,_||_| |_| \__, |
                                                                  __/ |
                                                                  |___/ '''
        # colors = [
        #     '\033[31m',  # 红色
        #     '\033[33m',  # 黄色
        #     '\033[32m',  # 绿色
        #     '\033[36m',  # 青色
        #     '\033[34m',  # 蓝色
        #     '\033[35m',  # 紫色
        # ]
        #
        # for i, line in enumerate(logo.split('\n')):
        #     print(colors[i % len(colors)] + line)
        #     time.sleep(0.1)

        print(logo)

        print('项目开源免费禁止商业用途，仓库地址：https://github.com/HaiBooLang/AHNUYunRun')
        user_name = input('请输入用户名：')
        user_password = input('请输入用户密码：')
        map_key = input('请输入高德地图API：')
        yunrun = YunRun(user_name, user_password, map_key)
        yunrun.run()
    except Exception as e:
        print(e)
        print('发生错误，请截图并在 GitHub 上提出 issue')
        time.sleep(100)


    # pyinstaller --onefile --add-binary="%PYTHON_HOME%\DLLs\*.dll;." --icon=yunrun.ico yunrun.py
