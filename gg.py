import streamlit as st
import socket
import threading
import time
from datetime import datetime
import queue

class ProxyServer:
    def __init__(self):
        self.server_socket = None
        self.is_running = False
        self.connections = []
        self.log_queue = queue.Queue()
        
    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_queue.put(log_entry)
        
    def handle_client(self, client_socket, client_address):
        try:
            request = client_socket.recv(1024)
            self.log_message(f"Connection from {client_address}")
            self.log_message(f"Request: {request[:100]}...")  # Log first 100 chars
            
            if not request:
                return
                
            # Parse request
            request_lines = request.split(b'\n')
            if len(request_lines) == 0:
                return
                
            first_line = request_lines[0].split()
            if len(first_line) < 2:
                return
                
            url = first_line[1]
            
            # Parse the URL to extract the host and port
            http_pos = url.find(b'://')
            if http_pos == -1:
                temp = url
            else:
                temp = url[(http_pos+3):]
                
            port_pos = temp.find(b':')
            webserver_pos = temp.find(b'/')
            
            if webserver_pos == -1:
                webserver_pos = len(temp)
                
            webserver = ""
            port = -1
            
            if (port_pos == -1 or webserver_pos < port_pos):
                port = 80
                webserver = temp[:webserver_pos]
            else:
                port = int((temp[(port_pos+1):])[:webserver_pos-port_pos-1])
                webserver = temp[:port_pos]
                
            self.proxy_request(webserver, port, client_socket, request)
            
        except Exception as e:
            self.log_message(f"Error handling client: {str(e)}")
        finally:
            try:
                client_socket.close()
            except:
                pass
                
    def proxy_request(self, webserver, port, client_socket, request):
        try:
            self.log_message(f"Connecting to {webserver.decode()}:{port}")
            proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_socket.settimeout(10)  # Add timeout
            proxy_socket.connect((webserver.decode(), port))
            proxy_socket.send(request)
            
            while True:
                try:
                    response = proxy_socket.recv(4096)
                    if len(response) > 0:
                        client_socket.send(response)
                    else:
                        break
                except socket.timeout:
                    break
                except Exception as e:
                    self.log_message(f"Error in proxy communication: {str(e)}")
                    break
                    
            proxy_socket.close()
            
        except Exception as e:
            self.log_message(f"Error in proxy request: {str(e)}")
            
    def start_server(self, host, port):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((host, port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)  # Add timeout for accept()
            
            self.is_running = True
            self.log_message(f"Proxy server started on {host}:{port}")
            
            while self.is_running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    # Handle each client in a separate thread
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except socket.timeout:
                    continue  # Check if still running
                except Exception as e:
                    if self.is_running:
                        self.log_message(f"Server error: {str(e)}")
                    break
                    
        except Exception as e:
            self.log_message(f"Failed to start server: {str(e)}")
        finally:
            self.stop_server()
            
    def stop_server(self):
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        self.log_message("Proxy server stopped")

# Initialize session state
if 'proxy_server' not in st.session_state:
    st.session_state.proxy_server = ProxyServer()
    st.session_state.server_thread = None
    st.session_state.logs = []

# Streamlit UI
st.title("🌐 Proxy Server Manager")
st.markdown("---")

# Server Configuration
col1, col2 = st.columns(2)

with col1:
    host = st.text_input("Host Address", value="127.0.0.1")
    
with col2:
    port = st.number_input("Port", min_value=1, max_value=65535, value=8888)

# Server Controls
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("🚀 Start Server", type="primary"):
        if not st.session_state.proxy_server.is_running:
            # Start server in a separate thread
            st.session_state.server_thread = threading.Thread(
                target=st.session_state.proxy_server.start_server,
                args=(host, port)
            )
            st.session_state.server_thread.daemon = True
            st.session_state.server_thread.start()
            st.success(f"Starting proxy server on {host}:{port}")
        else:
            st.warning("Server is already running!")

with col2:
    if st.button("🛑 Stop Server", type="secondary"):
        if st.session_state.proxy_server.is_running:
            st.session_state.proxy_server.stop_server()
            st.success("Server stopped")
        else:
            st.info("Server is not running")

with col3:
    if st.button("🗑️ Clear Logs"):
        st.session_state.logs = []
        # Clear the queue
        while not st.session_state.proxy_server.log_queue.empty():
            try:
                st.session_state.proxy_server.log_queue.get_nowait()
            except queue.Empty:
                break

# Server Status
st.markdown("---")
status_col1, status_col2 = st.columns(2)

with status_col1:
    if st.session_state.proxy_server.is_running:
        st.success("🟢 Server Status: Running")
    else:
        st.error("🔴 Server Status: Stopped")

with status_col2:
    st.info(f"📍 Address: {host}:{port}")

# Configuration Instructions
st.markdown("---")
st.subheader("📋 How to Use")
st.markdown("""
1. **Start the Server**: Click "Start Server" to begin listening for connections
2. **Configure Your Browser**: Set your browser's HTTP proxy to the address shown above
3. **Browse the Web**: All HTTP requests will now go through this proxy server
4. **Monitor Activity**: Watch the logs below to see real-time proxy activity

**Proxy Settings:**
- HTTP Proxy: `{host}:{port}`
- HTTPS Proxy: Not supported (HTTP only)
""".format(host=host, port=port))

# Real-time Logs
st.markdown("---")
st.subheader("📊 Server Logs")

# Get new log messages
while not st.session_state.proxy_server.log_queue.empty():
    try:
        log_message = st.session_state.proxy_server.log_queue.get_nowait()
        st.session_state.logs.append(log_message)
    except queue.Empty:
        break

# Display logs
log_container = st.container()
with log_container:
    if st.session_state.logs:
        # Show last 50 log entries
        recent_logs = st.session_state.logs[-50:]
        for log in reversed(recent_logs):  # Show newest first
            st.text(log)
    else:
        st.info("No logs yet. Start the server and make some requests to see activity.")

# Auto-refresh
if st.session_state.proxy_server.is_running:
    time.sleep(1)
    st.rerun()

# Warning and Disclaimer
st.markdown("---")
st.warning("""
⚠️ **Important Notes:**
- This proxy server is for educational and testing purposes only
- It only supports HTTP traffic (not HTTPS)
- Use responsibly and in compliance with applicable laws
- The server runs on the same machine as this Streamlit app
""")

st.markdown("---")
st.markdown("*Built with Streamlit*")
