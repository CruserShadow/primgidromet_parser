import requests
import time

from parser_exception import PrimGidroMet, VariableNotFoundError, NotLoggedInError, ParseError, IncorrectPageError
from requests import HTTPError
from lxml import etree
from data_classes import Wind, Station, PeriodForecast, OneZoneForecast, Period
import datetime
from typing import Tuple
from zone import Zone

import json

def form_timestamp(date):
    return datetime.datetime.timestamp(datetime.datetime.strptime(date, "%d.%m.%Y %H:%M"))


def get_columns_headers_and_delete_it_from_list(tbl: list):
    return [key.text for key in list(tbl.pop(0))]


def request_cache(func):
    cache = dict()

    seconds_to_refresh = datetime.timedelta(seconds=600)
    actual_data = datetime.datetime.now()

    def cache_func(*args):
        nonlocal actual_data
        now = datetime.datetime.now()

        if now >= actual_data:
            actual_data = now + seconds_to_refresh
            cache.clear()

        try:
            return cache[args[0]]
        except KeyError:
            res = func(*args)
            cache[args[0]] = res
            return res

    return cache_func


class Primgidromet:

    def __init__(self, login, password):
        self.__HEADERS = {"Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
                          "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:35.0) Gecko/20100101 Firefox/35.0",
                          "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                          "Accept-Encoding": "gzip",
                          "Cache-Control": "max-age=0",
                          "Connection": "keep-alive",
                          "Origin": "http://amp.primorsky.primgidromet.ru"}

        self.__REQUEST_POST_BODY = {"__EVENTTARGET": "",
                                    "__EVENTARGUMENT": "",
                                    "__VIEWSTATE": None,
                                    "__VIEWSTATEGENERATOR": None,
                                    "__EVENTVALIDATION": None,
                                    "ctl01$CentralHolder$MLogin$UserName": login,
                                    "ctl01$CentralHolder$MLogin$Password": password,
                                    "ctl01$CentralHolder$MLogin$LoginButton": None}

        self.LOGIN_URL = "http://amp.primorsky.primgidromet.ru/LoginPage.aspx"

        self.BASE_ZONE_URL = "http://amp.primorsky.primgidromet.ru/Templates/TemplateForAmp/"

        self.__session = requests.Session()
        self.__session.headers = self.__HEADERS

    def __parse_login_page_for_auth_headers(self, body):
        """
        This func finds variables in html document of login page to bypass protection
        :param body:
        :return:
        """
        doc = etree.HTML(body).xpath("./body/form")[0]
        try:
            self.__REQUEST_POST_BODY["__VIEWSTATE"] = doc.xpath('./div/input[@id="__VIEWSTATE"]')[0].get("value")
            self.__REQUEST_POST_BODY["__EVENTVALIDATION"] = doc.xpath('./div/input[@id="__EVENTVALIDATION"]')[0].get(
                "value")
            self.__REQUEST_POST_BODY["__VIEWSTATEGENERATOR"] = doc.xpath('./div/input[@id="__VIEWSTATEGENERATOR"]')[
                0].get("value")
            self.__REQUEST_POST_BODY["ctl01$CentralHolder$MLogin$LoginButton"] = \
                doc.xpath('//input[@id="ctl01_CentralHolder_MLogin_LoginButton"]')[0].get("value")
        except IndexError:
            raise VariableNotFoundError("Some variables were not found in html, check xpath")

    def __send_login_request(self):
        """
        Func tries login to site
        :return:
        """
        try:
            res = self.__session.post(self.LOGIN_URL, data=self.__REQUEST_POST_BODY)
        except HTTPError as err:
            raise err

        body = res.content.decode(res.apparent_encoding)

        if "kit.js" in body:
            print(f"- Successfully logged in (code:{res.status_code}) -")
            return
        else:
            raise NotLoggedInError(f"You are not logged in (code:{res.status_code}). Check credentials, headers, "
                                   f"cookies, method, structure of site")

    def login(self):
        try:
            response = self.__session.get(self.LOGIN_URL, headers=self.__HEADERS)
            response.raise_for_status()
        except HTTPError as err:
            raise err
        else:
            try:
                self.__parse_login_page_for_auth_headers(response.content.decode(response.apparent_encoding))
            except VariableNotFoundError as err:
                raise err
            try:
                self.__send_login_request()
            except NotLoggedInError as err:
                raise err

    @request_cache
    def send_request_to_get_page_html(self, place):
        try:

            res = self.__session.get(f"{self.BASE_ZONE_URL}{place}",
                                     headers=self.__HEADERS)
            res.raise_for_status()

            return res.content.decode(res.apparent_encoding)
        except HTTPError as err:
            raise err

    def parse_weather_forecast(self, place):

        def iter_elements_in_trs_and_parse_data(trs):
            cache_tuple = tuple()
            for tr in trs:
                cache_dict = {}
                for i, td in enumerate(tr.getchildren()):
                    cache_dict[columns[i]] = td.text

                cache_tuple += (cache_dict,)
            return cache_tuple

        try:
            html_body = self.send_request_to_get_page_html(place)
        except HTTPError as err:
            raise err

        else:
            if "Прогноз погоды" in html_body:
                html_element = etree.HTML(html_body)
            else:
                raise ParseError("Got incorrect site")

            tables = html_element.xpath('//span[@class="datatable"]/table')

            dict_forecast_for_return = {}

            for tab in tables:
                title = tab.xpath('../div[@class="section_header"]')[0]
                trs = tab.getchildren()
                del trs[0]  # deleting red title (check site)
                columns = get_columns_headers_and_delete_it_from_list(trs)
                weather_forecast_data = iter_elements_in_trs_and_parse_data(trs)
                dict_forecast_for_return[title.text] = weather_forecast_data

            return dict_forecast_for_return

    def parse_stations(self, place):

        def collect_data(table, col):

            collected_data = []
            for tr in table:
                data_cache = {}

                for i, td in enumerate(tr):
                    if col[i] == "Ветер":
                        data_cache[col[i]] = td.text.replace("&nbsp", " ")
                    else:
                        data_cache[col[i]] = td.text

                collected_data.append(data_cache)
            return collected_data

        try:
            html_body = self.send_request_to_get_page_html(place)
        except HTTPError as err:
            raise err

        else:

            if "Текущие метеоданные" in html_body:
                html_element = etree.HTML(html_body)
            else:
                raise ParseError("Got incorrect site")

            table = html_element.xpath('//table[@class="datatable"]')[0].getchildren()

            columns = get_columns_headers_and_delete_it_from_list(table)
            data = collect_data(table, columns)
            return data

    @staticmethod
    def get_stations(data: list) -> Tuple[Station]:
        returned_tuple = tuple()
        for station_info in data:
            try:
                direction, wind_speed = station_info.get("Ветер").split(", ")
            except ValueError:
                wind_speed = station_info.get("Ветер")
                direction = None

            wind = Wind(direction=direction,
                        wind_speed=wind_speed)
            stat = Station(name=station_info.get("Станция"), time=form_timestamp(station_info.get("Время наблюдения")),
                           wind=wind)
            returned_tuple += (stat,)
        return returned_tuple

    @staticmethod
    def get_weather_forecast(forecast: dict) -> Tuple[OneZoneForecast]:

        all_forecast_zones_tuple = tuple()

        for zone in forecast.keys():
            one_zone = OneZoneForecast(zone_name=zone)

            for period in forecast[zone]:
                try:
                    wind_direction = period["Направление ветра"]
                    wind_speed = period["Скорость ветра"]
                    atmosphere = period["Атмосферные явления"]
                    precipitation = period["Осадки"]
                    visibility = period["Видимость"]
                    wave_height = period["Высота волн"]
                    temperature = tuple(int(x) for x in period["Температура воздуха"].replace(" °C", "").split("..."))
                except KeyError as err:
                    raise ParseError(f"Some information was not found {err} {type(err)}")

                else:
                    wind_info = Wind(wind_speed=wind_speed, direction=wind_direction)
                    if period.get("Период прогноза") == "Ночь":
                        per = Period.night.value
                        one_zone.night = PeriodForecast(forecast_period=per, wind_info=wind_info,
                                                        atmosphere=atmosphere,
                                                        precipitation=precipitation,
                                                        visibility=visibility, wave_height=wave_height,
                                                        temperature=temperature)
                    else:
                        per = Period.daylight.value
                        day_period_dataclass = PeriodForecast(forecast_period=per, wind_info=wind_info,
                                                              atmosphere=atmosphere,
                                                              precipitation=precipitation,
                                                              visibility=visibility, wave_height=wave_height,
                                                              temperature=temperature)
                        one_zone.day = day_period_dataclass
                all_forecast_zones_tuple += (one_zone,)

            return all_forecast_zones_tuple


if __name__ == '__main__':
    with open("creds.json", "r") as creds:
        data = json.loads(creds.read())

    p = Primgidromet(data["login"], data["password"])
    p.login()

    parsed_stations = p.parse_stations(Zone.vladivostok.value)
    stations_dataclass = p.get_stations(parsed_stations)

    for s in stations_dataclass:
        print(f"{s.name} - {s.wind.wind_speed} | {s.wind.direction} | Время: {s.time}")

    forecast = p.parse_weather_forecast(Zone.vladivostok.value)
    print(p.get_weather_forecast(forecast))
