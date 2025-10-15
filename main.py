import json
import socket
import time
import get_port
import flask
import threading


app = flask.Flask(__name__)


class DeviceList:
    def __init__(self):
        port = 5000  # 设置端口
        """
        这是一种示例方式
        port = get_free_port()  # 自动获取空闲端口
    
        with open('D:/Desktop/python工具/局域网设备列表.html', 'w', encoding='utf-8') as f:
            f.write(f'<meta http-equiv="refresh" content="0;url=http://127.0.0.1:{port}/">')
        """

        self.post_lock_pool = []
        self.devices = []
        self.devices_port = {}
        self.lock = threading.Lock()
        self.port_lock = threading.Lock()
        self.marked_equipment = json.load(open('data.json', 'r'))

        threading.Thread(target=self.port_lock_func).start()

        app.add_url_rule('/__gnip__', view_func=self.gnip, methods=['POST'])
        app.add_url_rule('/<path:path>', view_func=self.router, methods=['GET'])
        app.add_url_rule('/device_list', view_func=self.device_list, methods=['GET'])
        app.add_url_rule('/add', view_func=self.add, methods=['POST'])
        app.add_url_rule('/remove', view_func=self.remove, methods=['POST'])
        app.add_url_rule('/port_list', view_func=self.port)
        app.add_url_rule('/', view_func=self.main_page, methods=['GET'])
        app.run(port=port)

    def port_lock_func(self):  # 限制后台扫端口总速度
        while True:
            if not self.post_lock_pool:
                self.post_lock_pool.append(True)

    def gnip(self):
        if flask.request.json['type']:
            self.devices = flask.request.json['device_list']
            def f():
                for item in self.devices:
                    if item[1] not in self.devices_port:
                        self.devices_port[item[1]] = lambda mac=item[1], ip=item[0]: get_port.GetPort(ip, self, mac)

                    if item[1] in [mac for _, mac, _ in self.marked_equipment] and type(self.devices_port[item[1]]) != get_port.GetPort:  # 优先后台加载收藏
                        self.devices_port[item[1]] = self.devices_port[item[1]]()

            threading.Thread(target=f).start()


        return {'message': 200}

    def router(self, path):
        try:
            return flask.send_file('pages/'+path)
        except Exception:
            return '404 not found', 404

    def main_page(self):
        return flask.send_file('pages/main.html')

    def device_list(self):
        marked_equipment = self.marked_equipment

        for item in marked_equipment:
            if item[1] in [mac for _, mac in self.devices]:
                item[2] = [ip for ip, _ in self.devices][[mac for _, mac in self.devices].index(item[1])]
            else:
                item[2] = '离线'

        return [self.devices, marked_equipment]

    def add(self):
        mac = flask.request.json['mac']
        name = flask.request.json['name']
        if mac == 'N/A' or mac == 'null':
            return 'mac not found', 500

        self.marked_equipment.append([name, mac, '离线'])
        json.dump(self.marked_equipment, open('data.json', 'w'))
        return 'ok'

    def remove(self):
        mac = flask.request.json['mac']
        del self.marked_equipment[[mac for _, mac, _ in self.marked_equipment].index(mac)]
        json.dump(self.marked_equipment, open('data.json', 'w'))
        return 'ok'

    def port(self):
        mac = flask.request.args.get('mac')
        cont = []
        try:
            if type(self.devices_port[mac]) != get_port.GetPort:
                self.devices_port[mac] = self.devices_port[mac]()

            for item in self.devices_port:
                if type(self.devices_port[item]) == get_port.GetPort:
                    if item != mac:
                        self.devices_port[item].mode = True
                    else:
                        self.devices_port[item].mode = '1'

            for item in self.devices_port[mac].port_list.copy():
                cont.append(
                    (item, self.devices_port[mac].port_list[item])
                )

            return cont
        except Exception:
            return cont


def get_free_port():
    """获取一个系统空闲的端口号"""
    # 创建一个TCP socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # 绑定到0.0.0.0的0端口，让系统自动分配空闲端口
        s.bind(('0.0.0.0', 0))
        # 获取实际分配的端口号
        _, port = s.getsockname()
    return port


if __name__ == '__main__':
    DeviceList()
