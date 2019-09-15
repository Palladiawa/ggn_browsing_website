#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
import sys
import json
import configparser
import time

import click
import requests
from bs4 import BeautifulSoup


HEADERS = {
    'User-Agent': ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/72.0.3626.121 Safari/537.36")
}


class GGn(object):

    def __init__(self, timeout=60):
        self.timeout = timeout

        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.history_path = os.path.join(dir_path, "history.json")
        self.config_path = os.path.join(dir_path, "config.ini")
        self.cookies_path = os.path.join(dir_path, "ggn.cookies")
        self.captcha_path = os.path.join(dir_path, "captcha.jpg")

        self.username = None
        self.password = None

        self.config = configparser.ConfigParser()
        self.load_config()

        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.cookies = None
        self.load_cookies()

        if not self.cookies and not self.username:
            self.ask_for_account()

        self.test_credentials()

        self.history = {}
        self.load_history()

        self.freeleech_torrents = {}
        self.smallest_torrents = {}

    def ask_for_account(self):
        self.username = click.prompt("Username", type=str)
        self.password = click.prompt("Password", type=str)
        self.config['Account'] = {}
        self.config['Account']['username'] = self.username
        self.config['Account']['password'] = self.password
        self.save_config()
        click.echo("-")

    def save_config(self):
        with open(self.config_path, 'w', encoding='utf-8') as configfile:
            self.config.write(configfile)

    def load_config(self):
        if os.path.isfile(self.config_path):
            self.config.read(self.config_path)
            self.username = self.config['Account']['username']
            self.password = self.config['Account']['password']

    def save_cookies(self):
        self.cookies = self.s.cookies.get_dict()
        with open(self.cookies_path, 'w', encoding='utf-8') as f:
            json.dump(self.cookies, f, indent=4, ensure_ascii=False)

    def load_cookies(self):
        if not os.path.isfile(self.cookies_path):
            return
        with open(self.cookies_path, 'r', encoding='utf-8') as f:
            self.cookies = json.load(f)
            self.s.cookies.update(self.cookies)

    def clear_cookies(self):
        self.s.cookies.clear()
        self.cookies = None
        try:
            os.remove(self.cookies_path)
        except OSError:
            pass

    def save_history(self):
        with open(self.history_path, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=4)
        click.echo(f"Saved {len(self.history)} torrents history")

    def load_history(self):
        if os.path.isfile(self.history_path):
            with open(self.history_path, 'r', encoding='utf-8') as f:
                self.history = json.load(f)
        #click.echo(f"Loaded {len(self.history)} torrents history")

    def test_credentials(self):
        url = "https://gazellegames.net"
        r = self.s.get(url, allow_redirects=False, timeout=self.timeout)
        r.raise_for_status()
        if r.status_code == 200:
            return
        self.clear_cookies()
        self.login()

    def login(self):
        click.echo("Logging in ...")

        login_url = "https://gazellegames.net/login.php"
        r = self.s.get(login_url, timeout=self.timeout)
        r.raise_for_status()

        if "nav_userinfo" in r.text:
            click.echo("Already logged in")
            click.echo("-")
            return

        if "banned from logging" in r.text:
            soup = BeautifulSoup(r.text, 'html.parser')
            maincontent_tag = soup.find(id="maincontent")
            warning_tags = maincontent_tag.find_all(class_="warning")
            click.echo("-")
            for warning_tag in warning_tags:
                click.echo(warning_tag.get_text().strip())
            sys.exit(1)

        soup = BeautifulSoup(r.text, 'html.parser')

        login_form_tag = soup.find(id="loginform")
        captcha_id = login_form_tag.find('input', {'name': 'image'})['value']
        captcha_url = login_form_tag.img['src']

        answers = []
        captcha_answers_tag = login_form_tag.find(id="captcha_answer")
        for captcha_answer_tag in captcha_answers_tag.find_all('li'):
            answer_id = captcha_answer_tag.input['value']
            answer_text = captcha_answer_tag.label.get_text()
            answers.append((answer_id, answer_text))

        r = self.s.get(captcha_url, timeout=self.timeout)
        r.raise_for_status()
        with open(self.captcha_path, 'wb') as f:
            f.write(r.content)

        click.launch(self.captcha_path)

        for index, (answer_id, answer_text) in enumerate(answers):
            click.echo(f"{index + 1}) {answer_text}")

        while True:
            choice = click.prompt("Choose captcha answer", type=int)
            if choice < 1 or choice > len(answers):
                click.echo("Bad choice!")
            else:
                break

        chosen_answer_id, chosen_answer_text = answers[choice - 1]

        data = {
            'image': captcha_id,
            'captcha': chosen_answer_id,
            'username': self.username,
            'password': self.password,
            'keeplogged': "1",
            'login': "Login",
        }

        r = self.s.post(login_url, data=data, timeout=self.timeout)
        r.raise_for_status()

        if r.url == login_url and "googleauth" in r.text:
            authkey = click.prompt("2-factor auth code")
            data = {
                'act': "authorize",
                'login': "Login",
                'authkey': authkey,
            }
            r = self.s.post(login_url, data=data, timeout=self.timeout)
            r.raise_for_status()

        if r.url == login_url:
            click.echo("-")
            click.echo("Login failed!")
            soup = BeautifulSoup(r.text, 'html.parser')
            maincontent_tag = soup.find(id="maincontent")
            warning_tags = maincontent_tag.find_all(class_="warning")
            for warning_tag in warning_tags:
                click.echo(warning_tag.get_text().strip())
            click.echo("-")
            self.ask_for_account()
            return self.login()

        self.save_cookies()

        click.echo("✔ Successfully logged in!")
        click.echo("-")

    def browse_website(self):
        url = "https://gazellegames.net"
        r = self.s.get(url, timeout=self.timeout)
        # print(r.text)
        m = re.findall(r'href="/.*?"', r.text)
        print(len(m))
        time.sleep(3)
        




if __name__ == "__main__":
    ggn = GGn(timeout=60)
    ggn.browse_website()
	
