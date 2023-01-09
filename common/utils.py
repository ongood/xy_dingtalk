import datetime
import functools
import asyncio


def aio_func(func):
    """
    Decorator to run a function in a new event loop
    :param func:
    :return:
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(func(*args, **kwargs))
        finally:
            loop.close()
        return result
    return wrapper


def get_now_time_str():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def list_to_str(target_list, join_str=','):
    """
    convert list to str
    :param target_list: list or None
    :param join_str: join str
    :return:
    """
    if target_list is None:
        return target_list
    return join_str.join(target_list)