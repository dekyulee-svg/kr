import streamlit as st
import socket
import threading
import struct
from concurrent.futures import ThreadPoolExecutor
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SOCKS5Proxy:
    def __init__(self, host='0.0.0.0', port=1080):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=100)
        
    def start_server(self):
        """启动SOCKS5代理服务器"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(100)
            self.running = True
            
            logger.info(f"SOCKS5 代理服务器启动: {self.host}:{self.port}")
            
            while self.running:
                try:
                    client_socket, addr = self.server_socket.accept()
                    self.executor.submit(self.handle_client, client_socket)
                except Exception as e:
                    if self.running:
                        logger.error(f"接受连接时出错: {e}")
                        
        except Exception as e:
            logger.error(f"启动服务器时出错: {e}")
            
    def handle_client(self, client_socket):
        """处理客户端连接"""
        try:
            # SOCKS5 握手 - 支持无认证
            if not self.socks5_handshake(client_socket):
                client_socket.close()
                return
                
            # 处理连接请求
            if not self.handle_connect_request(client_socket):
                client_socket.close()
                return
                
        except Exception as e:
            logger.error(f"处理客户端时出错: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
            
    def socks5_handshake(self, client_socket):
        """SOCKS5 握手过程 - 无需认证"""
        try:
            # 接收客户端握手请求
            data = client_socket.recv(256)
            if len(data) < 3:
                return False
                
            version, nmethods = struct.unpack('!BB', data[:2])
            if version != 5:
                return False
                
            methods = struct.unpack('!' + 'B' * nmethods, data[2:2+nmethods])
            
            # 支持无认证方法 (0x00)
            if 0x00 in methods:
                # 响应选择无认证
                response = struct.pack('!BB', 5, 0x00)
                client_socket.send(response)
                return True
            else:
                # 不支持的认证方法
                response = struct.pack('!BB', 5, 0xFF)
                client_socket.send(response)
                return False
                
        except Exception as e:
            logger.error(f"握手过程出错: {e}")
            return False
            
    def handle_connect_request(self, client_socket):
        """处理连接请求"""
        try:
            # 接收连接请求
            data = client_socket.recv(256)
            if len(data) < 10:
                return False
                
            version, cmd, reserved, address_type = struct.unpack('!BBBB', data[:4])
            
            if version != 5 or cmd != 1:  # 只支持CONNECT命令
                self.send_error_response(client_socket, 0x07)
                return False
                
            # 解析目标地址和端口
            if address_type == 1:  # IPv4
                target_host = socket.inet_ntoa(data[4:8])
                target_port = struct.unpack('!H', data[8:10])[0]
            elif address_type == 3:  # 域名
                domain_len = data[4]
                target_host = data[5:5+domain_len].decode('utf-8')
                target_port = struct.unpack('!H', data[5+domain_len:7+domain_len])[0]
            elif address_type == 4:  # IPv6
                target_host = socket.inet_ntop(socket.AF_INET6, data[4:20])
                target_port = struct.unpack('!H', data[20:22])[0]
            else:
                self.send_error_response(client_socket, 0x08)
                return False
                
            # 连接到目标服务器
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(15)
            
            try:
                target_socket.connect((target_host, target_port))
                
                # 发送成功响应
                response = struct.pack('!BBBB', 5, 0, 0, 1)  # IPv4
                response += socket.inet_aton('0.0.0.0')
                response += struct.pack('!H', 0)
                client_socket.send(response)
                
                # 开始数据转发
                self.relay_data(client_socket, target_socket)
                return True
                
            except Exception as e:
                self.send_error_response(client_socket, 0x05)
                target_socket.close()
                return False
                
        except Exception as e:
            logger.error(f"处理连接请求时出错: {e}")
            return False
            
    def send_error_response(self, client_socket, error_code):
        """发送错误响应"""
        try:
            response = struct.pack('!BBBB', 5, error_code, 0, 1)
            response += socket.inet_aton('0.0.0.0')
            response += struct.pack('!H', 0)
            client_socket.send(response)
        except:
            pass
        
    def relay_data(self, client_socket, target_socket):
        """双向数据转发"""
        def forward(source, destination):
            try:
                while True:
                    data = source.recv(4096)
                    if not data:
                        break
                    destination.send(data)
            except:
                pass
            finally:
                try:
                    source.close()
                    destination.close()
                except:
                    pass
                
        # 创建两个线程进行双向转发
        client_to_target = threading.Thread(target=forward, args=(client_socket, target_socket), daemon=True)
        target_to_client = threading.Thread(target=forward, args=(target_socket, client_socket), daemon=True)
        
        client_to_target.start()
        target_to_client.start()
        
        client_to_target.join()
        target_to_client.join()

# 自动启动 SOCKS5 服务器
def auto_start_proxy():
    """自动启动代理服务器"""
    if 'proxy_server' not in st.session_state:
        st.session_state.proxy_server = SOCKS5Proxy('0.0.0.0', 1080)
        st.session_state.server_thread = threading.Thread(
            target=st.session_state.proxy_server.start_server,
            daemon=True
        )
        st.session_state.server_thread.start()
        st.session_state.server_running = True

def main():
    # 自动启动代理服务器
    auto_start_proxy()
    
    # 空白页面
    pass

if __name__ == "__main__":
    main()
