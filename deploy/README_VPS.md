# Руководство по развёртыванию на микро-VPS (1 vCPU, 1 GB RAM) и Failover (EndoChat)

## 1. Ресурсный профиль
- **ОЗУ в покое**: ~115–135 МБ.
- **ОЗУ в пике (LLM / Vision / Web Search)**: до ~280–300 МБ (жестко ограничено семафором `MAX_CONCURRENT_SUBPROCESSES=2`).
- **Бюджет 1 GB RAM**:
  - ОС Linux + systemd: ~150 МБ.
  - EndoChat (основа + подпроцессы): ~300 МБ.
  - Свободно в физической памяти: **~530 МБ**.
  - **Swapfile**: **2 GB** (обязателен для предотвращения срабатывания OOM Killer при спайках).

---

## 2. Первоначальное развёртывание на VPS

1. **Создайте VPS**: Debian 12 или Ubuntu 24.04 (1 vCPU, 1 GB RAM, SSD от 10 ГБ).
2. **Скопируйте репозиторий на сервер**:
   ```bash
   # На локальной машине:
   scp -r C:\Users\danat\Desktop\endochat user@your_vps_ip:/tmp/endochat_deploy
   ```
3. **Запустите скрипт автонастройки на VPS под root**:
   ```bash
   ssh root@your_vps_ip
   mv /tmp/endochat_deploy /opt/endochat
   cd /opt/endochat
   chmod +x deploy/setup_micro_vps.sh
   ./deploy/setup_micro_vps.sh
   ```
4. **Скопируйте `.env` и проверьте права**:
   ```bash
   chmod 600 /opt/endochat/.env
   chown botrunner:botrunner /opt/endochat/.env
   ```
5. **Запустите службу**:
   ```bash
   sudo systemctl start endochat.service
   sudo systemctl status endochat.service
   ```

---

## 3. Двусторонний Failover (Переключение между VPS и локальным ПК)

### 3.1 Забрать бота с сервера на локальный ПК (Switch to Local)
*Когда нужно поковырять код локально, провести тесты или при плановых работах на сервере:*
```powershell
# Из корня endochat на рабочей станции:
.\scripts\switch_to_local.ps1 -Vps botrunner@your_vps_ip -Key C:\path\to\id_rsa
```
**Что происходит под капотом (автоматически):**
1. Скрипт гасит службу `endochat` на VPS (защита от **Split-Brain** и дублирования ответов).
2. На VPS выполняется `snapshot_backup.py`: сброс SQLite WAL + создание горячего снапшота базы и состояний.
3. Свежий снапшот скачивается на локальную машину.
4. Локальная база и `assistant_state.json` обновляются и проверяются через `PRAGMA integrity_check`.
5. Бот готов к локальному запуску через `.\start.bat`.

### 3.2 Вернуть бота обратно на сервер (Switch to VPS)
*Когда локальные тесты/работы завершены и пора вернуть бота в боевой режим на сервере:*
```powershell
# 1. Остановите локального бота (закройте окно start.bat / Ctrl+C)
# 2. Выполните возврат:
.\scripts\switch_to_vps.ps1 -Vps botrunner@your_vps_ip -Key C:\path\to\id_rsa
```
**Что происходит под капотом:**
1. Локально сбрасывается WAL базы данных и создается снапшот.
2. Снапшот загружается на VPS по SCP.
3. На VPS распаковывается актуальная база и состояния.
4. Служба `endochat.service` запускается на сервере и проверяется её статус.

---

## 4. Полезные команды на VPS
- **Просмотр логов в реальном времени**: `sudo journalctl -u endochat.service -f`
- **Просмотр логов файла бота**: `tail -f /opt/endochat/bot.log`
- **Перезапуск**: `sudo systemctl restart endochat.service`
- **Остановка**: `sudo systemctl stop endochat.service`
- **Потребление памяти процессом**: `systemctl status endochat.service | grep Memory`
