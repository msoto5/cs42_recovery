import argparse
import subprocess
import pandas as pd
from io import StringIO
from browser_history import get_history
from datetime import datetime, timedelta, date
import re
from dateutil.parser import parse, ParserError
import os.path
import time
import winreg
import enum


class DateParser(argparse.Action):
    def __call__(self, parser, namespace, values, option_strings=None):
        setattr(namespace, self.dest, parse(values).date())

def leer_argumentos():
    parser = argparse.ArgumentParser(
        description = "Analisis forense")
    
    parser.add_argument(
        "-i", "--initialdate",
        help = "Fecha inicial. Formato: 'Year'-'Month'-'Day' as YYYY-MM-DD. Example: 2022-08-31",
        metavar = "DATE",
        action = DateParser,
        #type = lambda s: datetime.strptime(s, '%Y-%m-%d')
    )
    parser.add_argument(
        "-f", "--finaldate",
        help = "Fecha final. Formato: 'Year'-'Month'-'Day' as YYYY-MM-DD. Example: 2022-08-31",
        metavar = "DATE",
        action = DateParser,
        #type = lambda s: datetime.strptime(s, '%Y-%m-%d')
    )
    parser.add_argument(
        "-I", "--initial_UNIX_date",
        help = "Fecha final. If -i is inserted, this flag -I will be ignored. Formato: unixtime. Example: 1661860019",
        metavar = "DATE"
        #type = lambda s: datetime.strptime(s, '%Y-%m-%d')
    )
    parser.add_argument(
        "-F", "--final_UNIX_date",
        help = "Fecha final. If -f is inserted, this flag -F will be ignored. Formato: unixtime. Example: 1661860019",
        metavar = "DATE"
        #type = lambda s: datetime.strptime(s, '%Y-%m-%d')
    )

    try:
        arg = parser.parse_args()

        if not arg.initialdate and arg.initial_UNIX_date:
            arg.initialdate = datetime.date(datetime.strptime(time.ctime(int(arg.initial_UNIX_date)), '%a %b %d %H:%M:%S %Y'))
        if not arg.finaldate and arg.final_UNIX_date:
            arg.finaldate = datetime.date(datetime.strptime(time.ctime(int(arg.final_UNIX_date)), '%a %b %d %H:%M:%S %Y'))

    except Exception:
        print("ERROR: Input arguments are wrong, run python3 recovery.py -h for help.")
        exit(1)
    
    return arg.initialdate, arg.finaldate


# Installed apps
sources = [
    [
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ],
    [
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    ],
    [
        winreg.HKEY_CURRENT_USER,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    ],
]

class ReadMode(enum.Enum):
   KEY = 1
   VALUE = 2

def read(key, mode):
    i = 0
    while True:
        try:
            if mode == ReadMode.KEY:
                yield winreg.EnumKey(key, i)
            elif mode == ReadMode.VALUE:
                yield winreg.EnumValue(key, i)
            i += 1
        except OSError:
            break

def readRegistery(keyType, registryKeyPath):
    registry = winreg.ConnectRegistry(None, keyType)
    registryKey = winreg.OpenKey(registry, registryKeyPath)
    for subKeyName in read(registryKey, ReadMode.KEY):
        subKey = winreg.OpenKey(registry, f"{registryKeyPath}\\{subKeyName}")
        values = {}
        for subKeyValue in read(subKey, ReadMode.VALUE):
            values[subKeyValue[0]] = subKeyValue[1]
        yield values

def installedApps():
    names = []
    for source in sources:
        for data in readRegistery(source[0], source[1]):

            if "InstallDate" in data:
                install_date = data["InstallDate"].strip()
            else:
                install_date = None
            if "DisplayName" in data:
                names.append([install_date, data['DisplayName'].strip(), data['DisplayVersion'].strip()])
    return names

def get_app_install_within_date(f_i, f_f):
    """
    Obtiene los programas instalados entre f_i y f_f
    """
    reg = installedApps()

    # Create dataframe
    df = pd.DataFrame(reg, columns=['InstallDate', 'Name', 'Version'])

    # Change first column from string to datetime object
    df['InstallDate'] = pd.to_datetime(df['InstallDate'], format='%Y%m%d').dt.date

    return df[(df["InstallDate"] >= f_i) & (df["InstallDate"] <= f_f)]


def print_app_install_within_date(f_i, f_f):

    df_installed_apps = get_app_install_within_date(f_i, f_f)
    print("\n==> Installed apps:")
    
    df_installed_apps.to_csv("recovery_app_installed.csv", index=False)
    
    if df_installed_apps.empty:
        print(f"There are no installed apps between {f_i} and {f_f}")
    else:
        print(df_installed_apps)
    print("")


# Browsing history
def get_browsing_history(f_i, f_f):
    """
    Obtiene el historial de busqueda de los navegadores
    """
    outputs = get_history()

    df = pd.read_csv(StringIO(outputs.to_csv()))

    df["Timestamp"] = pd.to_datetime(df['Timestamp'].str[:10], format='%Y-%m-%d').dt.date
    
    return df[(df["Timestamp"] >= f_i) & (df["Timestamp"] <= f_f)]

def print_browsing_history(f_i, f_f):

    print("\n==> Browsing History:")
    df_browsing_hist = get_browsing_history(f_inicial, f_final)
    df_browsing_hist.to_csv("recovery_browsing_history.csv", index=False)

    if df_browsing_hist.empty:
        print(f"There is no browsing history information between {f_inicial} and {f_final}")
    else:
        print(df_browsing_hist)
    print("")


# Recent files
def get_recent_files(carpeta, f_i, f_f):
    """
    Devuelve una lista con todos los ficheros, con unas determinadas
    extensiones, situados dentro del directorio 'carpeta' y sus
    subdirectorios.
    """

    if not os.path.isdir(carpeta):
        print("ERROR: No es una carpeta")
        exit(1)

    try:
        filedir_list = os.listdir(carpeta)
    except PermissionError:
        #print(f"Acces denied in {carpeta}")
        return []

    valid_files = []
    for fich in filedir_list:
        name = carpeta + '\\' + fich
        # Si es una carpeta, añadimos los ficheros de la subcarpeta
        if os.path.isdir(name):
            valid_files += get_recent_files(name, f_i, f_f)
            
        else:
            try:
                mod_time = datetime.strptime(time.ctime(os.path.getmtime(name)), '%a %b %d %H:%M:%S %Y')

                mod_time2 = datetime.date(mod_time)
                
                if (f_i <= mod_time2) & (f_f >= mod_time2):
                    data = [name, time.ctime(os.path.getctime(name)), mod_time, time.ctime(os.path.getatime(name))]
                    valid_files.append(data)

            except OSError:
                #print(f"file {fich} is not accessible")
                pass
            

    return valid_files

def print_recent_files(f_i, f_f):
    print("\n==> Recent Files:")
    df_recent_files = pd.DataFrame(get_recent_files(r"C:\Users\Miguel\Documents", f_i, f_f), columns=['Name', 'Creation Date', 'Modified Date', 'Access Date'])

    df_recent_files.to_csv("recovery_recent_files.csv", index=False)
    if df_recent_files.empty:
        print(f"There is no browsing history information between {f_inicial} and {f_final}")
    else:
        print(df_recent_files)

    print("")


# Archivos temporales
def print_temp_files(f_i, f_f):
    print("\n==> Temp Files:")
    df_temp_files = pd.DataFrame(get_recent_files(r"C:\Users\Miguel\AppData\Local\Temp", f_i, f_f), columns=['Name', 'Creation Date', 'Modified Date', 'Access Date'])

    df_temp_files.to_csv("recovery_temp_files.csv", index=False)
    if df_temp_files.empty:
        print(f"There is no browsing history information between {f_inicial} and {f_final}")
    else:
        print(df_temp_files)

    print("")

# Programas abiertos -> running processes
def print_open_programs():

    cmd = ['wmic', 'process', 'list', 'brief']
    Data = str(subprocess.check_output(cmd))

    # Regex to delete 2 or more spaces with comma
    a = re.sub(r'(  +)', ",", Data)

    # Indexing to eliminate "b' [...] '"
    a = a.replace("\\r\\r\\n", "\n")[2:-2].split(",\n")

    # Split each string in list
    a = [i.split(',') for i in a]
    # Eliminate last element of list because it is empty
    a.pop()

    # Create dataframe
    df = pd.DataFrame(a[1:], columns=a[0])

    df.to_csv("recovery_open_programs.csv", index=False)
    if df.empty:
        print(f"There is no browsing history information between {f_inicial} and {f_final}")
    else:
        print(df)



# MAIN
if __name__ == "__main__":

    default_time_days = 1
    f_inicial, f_final = leer_argumentos()
    
    today = date.today()

    # Check dates arguments
    if not f_inicial and not f_final:
        f_final = datetime.strftime(today, '%Y-%m-%d')
        f_inicial = datetime.strftime(today - timedelta(default_time_days), '%Y-%m-%d')
        
    elif not f_final:
        if f_inicial > today:
            print("\nERROR: Initial date is greater than today", today.strftime('%Y-%m-%d'))
            exit(1)
        else:
            f_final = f_inicial + timedelta(default_time_days)
        
    elif not f_inicial:
        if f_final > today:
            print("\nERROR: Final date is greater than today", today.strftime('%Y-%m-%d'))
            exit(1)
        else:
            f_inicial = f_inicial - timedelta(default_time_days)
    
    elif f_inicial > today or f_final > today:
        print("\nERROR: initial date or final date is greater than today", today.strftime('%Y-%m-%d'))
        exit(1)

    elif f_inicial > f_final:
        print("\nWARNING: initial date is greater than final date. Program will be run exchanging both dates.")
        f_inicial, f_final = f_final, f_inicial

    
    print("\nRealizando el recovery con:")
    print(f"- fecha inicial: {f_inicial}", type(f_inicial))
    print(f"- fecha final: {f_final}", type(f_final))

    # Get installed apps
    print_app_install_within_date(f_inicial, f_final)

    # Get browsing history
    print_browsing_history(f_inicial, f_final)

    # Get recent files
    print_recent_files(f_inicial, f_final)

    # Get temp_files
    print_temp_files(f_inicial, f_final)
    
    # Get open programs
    print_open_programs()

    # Resumen
    print("")
    print("Information with app installed saved in 'recovery_app_installed.csv'")
    print("Information with browsing history saved in 'recovery_browsing_history.csv'")
    print("Information with recent files saved in 'recovery_recent_files.csv'")
    print("Information with temp files saved in 'recovery_temp_files.csv'")
    print("Information with app installed saved in 'recovery_open_programs.csv'")
    print("")