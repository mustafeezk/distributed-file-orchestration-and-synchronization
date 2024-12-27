import socket
import signal
import sys
import json
import os
from pathlib import Path
from typing import Any

# Constants
CHUNK_SIZE = 4096
EOF_MARKER = b"<<EOF>>"

class ClientConnectionError(Exception):
    """Custom exception for connection errors"""
    pass

def signal_handler(sig: int, frame: Any) -> None:
    """Handle Ctrl+C signal"""
    print("\n[CLIENT SHUTDOWN] Signal received, closing client socket...")
    if 'client_socket' in globals():
        try:
            # Send exit command to server before closing
            command = {"action": "exit"}
            client_socket.send(json.dumps(command).encode('utf-8'))
        except:
            pass
    cleanup_and_exit()

def cleanup_and_exit():
    """Clean up resources and exit"""
    try:
        if 'client_socket' in globals():
            client_socket.close()
    except:
        pass
    print("[CLIENT SHUTDOWN] Connection closed")
    sys.exit(0)

def send_file(filename: str) -> bool:
    """Send file to server in chunks"""
    try:
        # First receive the initial response
        initial_response = json.loads(client_socket.recv(1024).decode('utf-8'))
        
        # Check if server is ready
        if initial_response.get("status") != "success":
            print(f"Server error: {initial_response.get('message', 'Unknown error')}")
            return False
            
        with open(filename, 'rb') as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    client_socket.send(EOF_MARKER)
                    break
                client_socket.send(chunk)
        return True
    except Exception as e:
        print(f"Error sending file: {e}")
        return False

def receive_file(filename: str) -> bool:
    """Receive file from server in chunks"""
    try:
        # First receive the initial response
        initial_response = json.loads(client_socket.recv(1024).decode('utf-8'))
        
        # Check if there was an error
        if initial_response.get("status") == "error":
            print(f"Error: {initial_response['message']}")
            return False
            
        try:
            with open(filename, 'wb') as f:
                while True:
                    chunk = client_socket.recv(CHUNK_SIZE)
                    if not chunk:
                        print("Connection closed unexpectedly")
                        os.remove(filename)  # Clean up partial file
                        return False
                    if chunk.endswith(EOF_MARKER):
                        f.write(chunk[:-len(EOF_MARKER)])  # Remove EOF marker
                        break
                    f.write(chunk)
            return True
        except Exception as e:
            # Clean up partial file if there's an error
            try:
                os.remove(filename)
            except:
                pass
            raise e
    except Exception as e:
        print(f"Error receiving file: {e}")
        return False

def display_menu() -> None:
    """Display the main menu"""
    print("\nAvailable commands:")
    print("1. Upload file")
    print("2. Download file")
    print("3. Preview file")
    print("4. Delete file")
    print("5. List files")
    print("6. Exit")

def get_valid_input(prompt: str, valid_choices: list) -> str:
    """Get valid input from user"""
    while True:
        choice = input(prompt)
        if choice in valid_choices:
            return choice
        print(f"Invalid input. Please choose from {', '.join(valid_choices)}")

def handle_upload_choice():
    """Handle the upload command with proper error handling"""
    filename = input("Enter file path to upload: ")
    if not os.path.exists(filename):
        print("File does not exist!")
        return
    
    command = {"action": "upload", "filename": Path(filename).name}
    client_socket.send(json.dumps(command).encode('utf-8'))
    if send_file(filename):
        print(f"File {filename} uploaded successfully")
    else:
        print("Upload failed")

def handle_download_choice():
    """Handle the download command with proper error handling"""
    filename = input("Enter filename to download: ")
    command = {"action": "download", "filename": filename}
    client_socket.send(json.dumps(command).encode('utf-8'))
    
    if receive_file(filename):
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            print(f"File {filename} downloaded successfully")
        else:
            print("Download failed: File is empty or was not created")
            try:
                os.remove(filename)
            except:
                pass
    else:
        print("Download failed")
        try:
            if os.path.exists(filename):
                os.remove(filename)
        except:
            pass

def handle_preview_choice():
    """Handle the preview command"""
    filename = input("Enter filename to preview: ")
    command = {"action": "preview", "filename": filename}
    client_socket.send(json.dumps(command).encode('utf-8'))
    response = json.loads(client_socket.recv(2048).decode('utf-8'))
    if response.get("status") == "shutdown":
        raise ClientConnectionError("Server shutdown received")
    if response["status"] == "success":
        print("\nFile preview:")
        print("-" * 40)
        print(response["preview"])
        print("-" * 40)
    else:
        print(f"Error: {response['message']}")

def check_server_shutdown():
    """Check for server shutdown message and handle accordingly"""
    try:
        client_socket.settimeout(0.1)  # Short timeout for checking messages
        try:
            data = client_socket.recv(1024)
            if data:
                try:
                    response = json.loads(data.decode('utf-8'))
                    if response.get("status") == "shutdown":
                        print("\n[SERVER SHUTDOWN] Server is shutting down. Closing connection...")
                        raise ClientConnectionError("Server shutdown received")
                except json.JSONDecodeError:
                    pass
        except socket.timeout:
            pass
    finally:
        client_socket.settimeout(None)  # Reset to blocking mode

def start_client() -> None:
    """Start the client and handle connection"""
    global client_socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        client_socket.connect(('127.0.0.1', 12345))
        
        # Initial handshake
        client_socket.send("HELLO".encode('utf-8'))
        response = client_socket.recv(1024).decode('utf-8')
        
        if response != "ACK":
            print("Handshake failed")
            return

        # Authentication
        username = input("Username: ")
        password = input("Password: ")
        
        auth_data = json.dumps({"username": username, "password": password})
        client_socket.send(auth_data.encode('utf-8'))
        
        auth_response = json.loads(client_socket.recv(1024).decode('utf-8'))
        if auth_response["status"] != "success":
            print(f"Authentication failed: {auth_response['message']}")
            return

        print("Authentication successful!")

        while True:
            try:
                # Check for server shutdown before displaying menu
                check_server_shutdown()
                
                display_menu()
                choice = get_valid_input("Enter your choice (1-6): ", ["1", "2", "3", "4", "5", "6"])
                
                # Check for server shutdown again after user input but before sending command
                check_server_shutdown()
                
                if choice == "1":  # Upload
                    handle_upload_choice()
                elif choice == "2":  # Download
                    handle_download_choice()
                elif choice == "3":  # Preview
                    handle_preview_choice()
                elif choice == "4":  # Delete
                    filename = input("Enter filename to delete: ")
                    command = {"action": "delete", "filename": filename}
                    client_socket.send(json.dumps(command).encode('utf-8'))
                    response = json.loads(client_socket.recv(1024).decode('utf-8'))
                    if response.get("status") == "shutdown":
                        raise ClientConnectionError("Server shutdown received")
                    print(response["message"])
                elif choice == "5":  # List files
                    command = {"action": "list"}
                    client_socket.send(json.dumps(command).encode('utf-8'))
                    response = json.loads(client_socket.recv(1024).decode('utf-8'))
                    if response.get("status") == "shutdown":
                        raise ClientConnectionError("Server shutdown received")
                    if response["status"] == "success":
                        print("\nYour files:")
                        for file in response["files"]:
                            print(f"- {file}")
                    else:
                        print(f"Error: {response['message']}")
                elif choice == "6":  # Exit
                    command = {"action": "exit"}
                    client_socket.send(json.dumps(command).encode('utf-8'))
                    print("[CLIENT SHUTDOWN] Exiting...")
                    break

            except json.JSONDecodeError:
                print("Error: Invalid response from server")
                break
            except socket.error as e:
                print(f"\nConnection lost: {e}")
                break
            except ClientConnectionError as e:
                print(f"\nConnection error: {e}")
                break
            except KeyboardInterrupt:
                print("\n[CLIENT SHUTDOWN] Ctrl+C received, closing connection...")
                break

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        cleanup_and_exit()

if __name__ == "__main__":
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    start_client()
