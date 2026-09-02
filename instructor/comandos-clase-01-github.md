# Comandos de la clase 1 — GitHub

> Notas de clase del instructor, tal como se dictaron.

```bash
--> Github

Versiones instaladas:

git --version
gpg --version
ssh -V

Configuración de Git:

git config --global --list


Claves SSH registradas en tu máquina:

ls -la ~/.ssh/
ssh-add -l


Probar conexión SSH con GitHub:

ssh -T git@github.com


Claves GPG registradas en tu máquina:

gpg --list-secret-keys --keyid-format=long
Verificar que la firma funciona:


echo "test" | gpg --clearsign```
