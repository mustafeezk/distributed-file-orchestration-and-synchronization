import socket
import threading
import signal
import sys
import os
import json
import time
from pathlib import Path
from typing import Dict, Union, Any, List

# Global variables for connection management
active_connections: List[socket.socket] = []
connections_lock = threading.Lock()

# Constants
SERVER_STORAGE = Path("server_storage")
CHUNK_SIZE = 4096
EOF_MARKER = b"<<EOF>>"

def cleanup_connections():
    """Cleanup all active connections"""
    with connections_lock:
        for client_socket in active_connections:
            try:
                # Send shutdown message to client and wait briefly
                shutdown_msg = json.dumps({"status": "shutdown", "message": "Server is shutting down"})
                client_socket.send(shutdown_msg.encode('utf-8'))
                time.sleep(0.1)  # Give clients time to receive the message
                client_socket.close()
            except:
                pass
        active_connections.clear()

def signal_handler(sig: int, frame: Any) -> None:
    """Handle shutdown signal"""
    print("\n[SERVER SHUTDOWN] Signal received, closing all connections...")
    cleanup_connections()
    print("[SERVER SHUTDOWN] All connections closed")
    server_socket.close()
    sys.exit(0)

def ensure_user_directory(username: str) -> Path:
    """Create user directory if it doesn't exist"""
    user_dir = SERVER_STORAGE / username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir

def authenticate_user(credentials: Dict[str, str]) -> bool:
    """Verify user credentials against id_passwd.txt"""
    try:
        with open("id_passwd.txt", "r", encoding='utf-8') as file:
            for line in file:
                stored_user, stored_pwd = line.strip().split(":")
                if stored_user == credentials["username"] and stored_pwd == credentials["password"]:
                    return True
        return False
    except Exception as e:
        print(f"Authentication error: {e}")
        return False

def handle_upload(client_socket: socket.socket, user_dir: Path, filename: str) -> Dict[str, str]:
    """Handle file upload from client"""
    try:
        # Send initial success response
        success_response = {"status": "success", "message": "Ready for file transfer"}
        client_socket.send(json.dumps(success_response).encode('utf-8'))
        
        file_path = user_dir / filename
        with open(file_path, 'wb') as f:
            while True:
                chunk = client_socket.recv(CHUNK_SIZE)
                if not chunk:
                    return {"status": "error", "message": "Connection lost during transfer"}
                if chunk.endswith(EOF_MARKER):
                    f.write(chunk[:-len(EOF_MARKER)])  # Remove EOF marker
                    break
                f.write(chunk)
        return {"status": "success", "message": f"File {filename} uploaded successfully"}
    except Exception as e:
        # Clean up partial file if there's an error
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass
        return {"status": "error", "message": str(e)}

def handle_download(client_socket: socket.socket, user_dir: Path, filename: str) -> Dict[str, str]:
    """Handle file download request"""
    try:
        file_path = user_dir / filename
        
        # First check if file exists in user's directory
        if not file_path.exists():
            error_response = {"status": "error", "message": "File not found in your directory"}
            client_socket.send(json.dumps(error_response).encode('utf-8'))
            return error_response
            
        # Check if the file is actually within the user's directory (security check)
        if not str(file_path.resolve()).startswith(str(user_dir.resolve())):
            error_response = {"status": "error", "message": "Access denied: You can only access files in your directory"}
            client_socket.send(json.dumps(error_response).encode('utf-8'))
            return error_response
        
        # Send success response first
        success_response = {"status": "success", "message": "Starting file transfer"}
        client_socket.send(json.dumps(success_response).encode('utf-8'))
        
        # Small delay to ensure response is received before file data
        time.sleep(0.1)
        
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    client_socket.send(EOF_MARKER)
                    break
                client_socket.send(chunk)
        return {"status": "success", "message": "File sent successfully"}
    except Exception as e:
        error_response = {"status": "error", "message": str(e)}
        try:
            client_socket.send(json.dumps(error_response).encode('utf-8'))
        except:
            pass
        return error_response

def handle_preview(user_dir: Path, filename: str) -> Dict[str, str]:
    """Preview first 1024 bytes of a file"""
    try:
        file_path = user_dir / filename
        if not file_path.exists():
            return {"status": "error", "message": "File not found"}
            
        # Security check
        if not str(file_path.resolve()).startswith(str(user_dir.resolve())):
            return {"status": "error", "message": "Access denied"}

        with open(file_path, 'rb') as f:
            preview = f.read(1024)
        return {"status": "success", "preview": preview.decode('utf-8', errors='ignore')}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def handle_delete(user_dir: Path, filename: str) -> Dict[str, str]:
    """Delete a file from user directory"""
    try:
        file_path = user_dir / filename
        if not file_path.exists():
            return {"status": "error", "message": "File not found"}
            
        # Security check
        if not str(file_path.resolve()).startswith(str(user_dir.resolve())):
            return {"status": "error", "message": "Access denied"}
        
        os.remove(file_path)
        return {"status": "success", "message": f"File {filename} deleted successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def list_files(user_dir: Path) -> Dict[str, Union[str, list]]:
    """List all files in user directory"""
    try:
        files = [f.name for f in user_dir.iterdir() if f.is_file()]
        return {"status": "success", "files": files}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def handle_client(client_socket: socket.socket, addr: tuple) -> None:
    """Handle individual client connection"""
    print(f"[NEW CONNECTION] {addr} connected.")
    
    # Add connection to active connections list
    with connections_lock:
        active_connections.append(client_socket)
    
    try:
        # Initial handshake
        message = client_socket.recv(1024).decode('utf-8')
        if message != "HELLO":
            client_socket.send("Invalid handshake".encode('utf-8'))
            return

        client_socket.send("ACK".encode('utf-8'))
        print(f"Connection successful with {addr}")

        # Authentication
        auth_data = client_socket.recv(1024).decode('utf-8')
        credentials = json.loads(auth_data)
        
        if not authenticate_user(credentials):
            client_socket.send(json.dumps({"status": "error", "message": "Authentication failed"}).encode('utf-8'))
            return

        user_dir = ensure_user_directory(credentials["username"])
        client_socket.send(json.dumps({"status": "success", "message": "Authentication successful"}).encode('utf-8'))
        print(f"User {credentials['username']} authenticated successfully")

        # Handle commands
        while True:
            try:
                command_data = client_socket.recv(1024).decode('utf-8')
                if not command_data:
                    break

                command = json.loads(command_data)
                response = {"status": "error", "message": "Invalid command"}

                if command["action"] == "upload":
                    response = handle_upload(client_socket, user_dir, command["filename"])
                    print(f"Upload request from {credentials['username']}: {response['status']}")
                elif command["action"] == "download":
                    response = handle_download(client_socket, user_dir, command["filename"])
                    print(f"Download request from {credentials['username']}: {response['status']}")
                elif command["action"] == "preview":
                    response = handle_preview(user_dir, command["filename"])
                elif command["action"] == "delete":
                    response = handle_delete(user_dir, command["filename"])
                    print(f"Delete request from {credentials['username']}: {response['status']}")
                elif command["action"] == "list":
                    response = list_files(user_dir)
                elif command["action"] == "exit":
                    print(f"User {credentials['username']} requested exit")
                    break

                # Only send response for non-file-transfer operations
                if command["action"] not in ["upload", "download"]:
                    client_socket.send(json.dumps(response).encode('utf-8'))

            except json.JSONDecodeError:
                print(f"[ERROR] Invalid JSON from client {addr}")
                break
            except Exception as e:
                print(f"[ERROR] {e}")
                break

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        # Remove connection from active connections list
        with connections_lock:
            if client_socket in active_connections:
                active_connections.remove(client_socket)
        try:
            client_socket.close()
        except:
            pass
        print(f"[DISCONNECTED] {addr} disconnected.")

def start_server() -> None:
    """Start the server and listen for connections"""
    global server_socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind(('0.0.0.0', 12345))
        server_socket.listen(5)
        print("[SERVER STARTED] Listening on port 12345")

        # Create server storage directory if it doesn't exist
        SERVER_STORAGE.mkdir(exist_ok=True)

        while True:
            try:
                client_socket, addr = server_socket.accept()
                client_thread = threading.Thread(target=handle_client, args=(client_socket, addr))
                client_thread.daemon = True  # Set thread as daemon
                client_thread.start()
                print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")
            except OSError:
                # Server socket was closed
                break
            except Exception as e:
                print(f"[ERROR] Accept failed: {e}")
                continue

    except Exception as e:
        print(f"[ERROR] Server failed to start: {e}")
    finally:
        cleanup_connections()
        try:
            server_socket.close()
        except:
            pass

if __name__ == "__main__":
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    start_server()
