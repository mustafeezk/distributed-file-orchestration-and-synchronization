import socket
import signal
import sys
import json
import os
from pathlib import Path
from typing import Any, Optional

CHUNK_SIZE = 4096
EOF_MARKER = b"<<EOF>>"

def signal_handler(sig: int, frame: Any) -> None:
    print("\n[CLIENT SHUTDOWN] Signal received, closing client socket...")
    client_socket.close()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def send_file(filename: str) -> bool:
    """Send file to server in chunks"""
    try:
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
        with open(filename, 'wb') as f:
            while True:
                chunk = client_socket.recv(CHUNK_SIZE)
                if chunk.endswith(EOF_MARKER):
                    f.write(chunk[:-len(EOF_MARKER)])  # Remove EOF marker
                    break
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Error receiving file: {e}")
        return False

def display_menu() -> None:
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

def start_client() -> None:
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
            display_menu()
            choice = get_valid_input("Enter your choice (1-6): ", ["1", "2", "3", "4", "5", "6"])

            if choice == "1":  # Upload
                filename = input("Enter file path to upload: ")
                if not os.path.exists(filename):
                    print("File does not exist!")
                    continue
                
                command = {"action": "upload", "filename": Path(filename).name}
                client_socket.send(json.dumps(command).encode('utf-8'))
                if send_file(filename):
                    response = json.loads(client_socket.recv(1024).decode('utf-8'))
                    print(response["message"])

            elif choice == "2":  # Download
                filename = input("Enter filename to download: ")
                command = {"action": "download", "filename": filename}
                client_socket.send(json.dumps(command).encode('utf-8'))
                if receive_file(filename):
                    print(f"File {filename} downloaded successfully")

            elif choice == "3":  # Preview
                filename = input("Enter filename to preview: ")
                command = {"action": "preview", "filename": filename}
                client_socket.send(json.dumps(command).encode('utf-8'))
                response = json.loads(client_socket.recv(1024).decode('utf-8'))
                if response["status"] == "success":
                    print("\nFile preview:")
                    print("-" * 40)
                    print(response["preview"])
                    print("-" * 40)
                else:
                    print(f"Error: {response['message']}")

            elif choice == "4":  # Delete
                filename = input("Enter filename to delete: ")
                command = {"action": "delete", "filename": filename}
                client_socket.send(json.dumps(command).encode('utf-8'))
                response = json.loads(client_socket.recv(1024).decode('utf-8'))
                print(response["message"])

            elif choice == "5":  # List files
                command = {"action": "list"}
                client_socket.send(json.dumps(command).encode('utf-8'))
                response = json.loads(client_socket.recv(1024).decode('utf-8'))
                if response["status"] == "success":
                    print("\nYour files:")
                    for file in response["files"]:
                        print(f"- {file}")
                else:
                    print(f"Error: {response['message']}")

            elif choice == "6":  # Exit
                command = {"action": "exit"}
                client_socket.send(json.dumps(command).encode('utf-8'))
                break

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        client_socket.close()

if __name__ == "__main__":
    start_client()
