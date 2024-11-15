import socket
import threading
import signal
import sys
import os
import json
from pathlib import Path
from typing import Dict, Union, Any

# Signal handler for graceful shutdown
def signal_handler(sig: int, frame: Any) -> None:
    print("\n[SERVER SHUTDOWN] Signal received, closing server socket...")
    server_socket.close()
    sys.exit(0)

# Attach the signal handler to SIGINT
signal.signal(signal.SIGINT, signal_handler)

SERVER_STORAGE = Path("server_storage")
CHUNK_SIZE = 4096
EOF_MARKER = b"<<EOF>>"

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
        file_path = user_dir / filename
        with open(file_path, 'wb') as f:
            while True:
                chunk = client_socket.recv(CHUNK_SIZE)
                if chunk.endswith(EOF_MARKER):
                    f.write(chunk[:-len(EOF_MARKER)])  # Remove EOF marker
                    break
                f.write(chunk)
        return {"status": "success", "message": f"File {filename} uploaded successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def handle_download(client_socket: socket.socket, user_dir: Path, filename: str) -> Dict[str, str]:
    """Handle file download request"""
    try:
        file_path = user_dir / filename
        if not file_path.exists():
            return {"status": "error", "message": "File not found"}
        
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    client_socket.send(EOF_MARKER)
                    break
                client_socket.send(chunk)
        return {"status": "success", "message": "File sent successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def handle_preview(user_dir: Path, filename: str) -> Dict[str, str]:
    """Preview first 1024 bytes of a file"""
    try:
        file_path = user_dir / filename
        if not file_path.exists():
            return {"status": "error", "message": "File not found"}
        
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
    print(f"[NEW CONNECTION] {addr} connected.")
    
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
                elif command["action"] == "download":
                    response = handle_download(client_socket, user_dir, command["filename"])
                elif command["action"] == "preview":
                    response = handle_preview(user_dir, command["filename"])
                elif command["action"] == "delete":
                    response = handle_delete(user_dir, command["filename"])
                elif command["action"] == "list":
                    response = list_files(user_dir)
                elif command["action"] == "exit":
                    break

                client_socket.send(json.dumps(response).encode('utf-8'))

            except json.JSONDecodeError:
                print(f"[ERROR] Invalid JSON from client {addr}")
                break
            except Exception as e:
                print(f"[ERROR] {e}")
                break

    finally:
        client_socket.close()
        print(f"[DISCONNECTED] {addr} disconnected.")

def start_server() -> None:
    global server_socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', 12345))
    server_socket.listen(5)  # Explicitly set backlog for Python 3.6+ compatibility
    print("[SERVER STARTED] Listening on port 12345")

    # Create server storage directory if it doesn't exist
    SERVER_STORAGE.mkdir(exist_ok=True)

    while True:
        try:
            client_socket, addr = server_socket.accept()
            client_thread = threading.Thread(target=handle_client, args=(client_socket, addr))
            client_thread.start()
            print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")
        except OSError:
            break

if __name__ == "__main__":
    start_server()
