from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.expected_conditions import presence_of_element_located
# from selenium.webdriver.firefox.options import Options

class router_base():

    def __init__(self):
        # firefox_options = Options()
        # firefox_options.add_argument("--headless")       # define headless
        # with webdriver.Firefox(firefox_options=firefox_options) as driver:
        self.driver = webdriver.Firefox()

    def close(self):
        self.driver.close()
        self.driver = None

    def login(self):
        pass

    def logout(self):
        pass

    def test(self):
        # wait = WebDriverWait(driver, 10)
        self.driver.get("http://www.python.org")
        # cookie = {‘name’ : ‘foo’, ‘value’ : ‘bar’}
        # driver.add_cookie(cookie)
        # driver.get_cookies()
        assert "Python" in self.driver.title
        elem = self.driver.find_element_by_name("q")
        elem.send_keys("pycon")
        elem.send_keys(Keys.RETURN)
        print(self.driver.page_source)

        # results = driver.find_elements_by_css_selector("h3>a")
        # for i, result in results.iteritems():
        #     print("#{}: {} ({})".format(i, result.text, result.get_property("href")))
        # driver.get_screenshot_as_file("./img/sreenshot1.png")

if __name__ == "__main__":
    router_base().test()