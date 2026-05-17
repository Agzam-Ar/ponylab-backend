import logs.plant_log
import logic.rules

from pretty_errors import configure, FILENAME_EXTENDED, replace_stderr  # pyright: ignore[reportUnknownVariableType, reportMissingTypeStubs]
import pretty_errors

replace_stderr()
# Настраиваем: выводить только файлы вашего проекта
configure(
    # --- КЛЮЧЕВЫЕ НАСТРОЙКИ ДЛЯ ВАШЕЙ ПРОБЛЕМЫ ---
    top_first=True,  # МЕНЯЕТ ПОРЯДОК: теперь ваш код и корень ошибки будут ВВЕРХУ (как в Java)
    always_display_bottom=False,  # Не дублировать ошибку в самом низу, если стек развернут
    stack_depth=0,  # 0 — выводить весь стек (без ограничений по глубине)
    # --- ЛОКАЛЬНЫЕ ПЕРЕМЕННЫЕ (Помогают понять контекст) ---
    display_locals=True,  # Показывать локальные переменные в месте падения
    display_trace_locals=False,  # Не спамить переменными на каждом шаге стека
    truncate_locals=True,  # Обрезать слишком длинные значения переменных
    # --- ВИЗУАЛЬНЫЕ ЭЛЕМЕНТЫ И СТРЕЛКИ ---
    display_arrow=True,  # Показывать стрелочку на проблемную строку
    arrow_head_character=">",  # Символ головы стрелки
    arrow_tail_character="-",  # Символ тела стрелки
    separator_character="-",  # Разделитель между кадрами стека
    line_length=0,  # Длина разделительной линии (0 — на всю ширину терминала)
    full_line_newline=False,
    # --- АНАЛИЗ КОДА ---
    lines_before=2,  # Сколько строк кода показывать ДО проблемной строки
    lines_after=1,  # Сколько строк кода показывать ПОСЛЕ
    trace_lines_before=1,  # Строки кода ДО для промежуточных кадров стека
    trace_lines_after=0,  # Строки кода ПОСЛЕ для промежуточных кадров стека
    truncate_code=False,  # Не обрезать строки кода
    # --- ОТОБРАЖЕНИЕ ИМЕН И ССЫЛОК ---
    filename_display=FILENAME_EXTENDED,  # Выводить относительный путь к файлу
    display_link=True,  # Выводить кликабельную ссылку на файл (для VS Code/PyCharm)
    line_number_first=True,  # Выводить номер строки перед именем файла
    display_timestamp=False,  # Отключить временную метку (убирает лишний текст)
    # --- ОБРАБОТКА ИСКЛЮЧЕНИЙ ---
    exception_above=False,  # Выводить текст ошибки ПОД кодом (True — НАД кодом)
    exception_below=True,
    show_suppressed=False,  # Не показывать подавленные исключения
    inner_exception_message="Внутреннее исключение:",
    inner_exception_separator=True,  # Визуально разделять цепочки ошибок (Chained Exceptions)
    # --- СИСТЕМНЫЕ НАСТРОЙКИ ---
    reset_stdout=False,  # Не сбрасывать стандартный вывод терминала
    name="my_config",
    prefix="",
    postfix="",
    infix="  ",
    # header_color=pretty_errors.BRIGHT_RED,
    # exception_color=pretty_errors.BRIGHT_RED,
    # exception_arg_color=pretty_errors.BRIGHT_YELLOW,
    # exception_file_color=pretty_errors.RED,
    # filename_color=pretty_errors.BRIGHT_CYAN,  # Ваши файлы будут ярко-голубыми
    # function_color=pretty_errors.BRIGHT_GREEN,  # Имена функций — зелеными
    # line_number_color=pretty_errors.CYAN,
    # line_color=pretty_errors.CYAN,
    # code_color=pretty_errors.WHITE,
    # arrow_head_color=pretty_errors.BRIGHT_GREEN,
    # arrow_tail_color=pretty_errors.GREEN,
    # local_name_color=pretty_errors.BRIGHT_MAGENTA,  # Имена переменных — розовыми
    # local_len_color=pretty_errors.MAGENTA,
    # local_value_color=pretty_errors.WHITE,
    # syntax_error_color=pretty_errors.BRIGHT_RED,
    # timestamp_color=pretty_errors.BRIGHT_BLACK,
    # link_color=pretty_errors.BRIGHT_BLACK,
)


class Config:
    rules: logic.rules.PlantRules = logic.rules.PlantRules()
    log: logs.plant_log.PlantLog = logs.plant_log.PlantLog()
