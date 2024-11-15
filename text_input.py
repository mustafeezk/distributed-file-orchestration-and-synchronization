# lst = []
# file = open("id_passwd.txt","a")
# id = input("Enter user id:")
# pwd = input("Enter pwd:")
# lst.append(id)
# lst.append(pwd)
# file.write(f"{id}:{pwd}\n")
# file.close()

file = open("id_passwd.txt","r")
text = file.read()
#print(text.split().split(":"))
for i in text.split():
    #print(i)
    print(i.split(":")[1])
        #print(word)
file.close
