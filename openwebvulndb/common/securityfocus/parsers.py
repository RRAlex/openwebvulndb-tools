# openwebvulndb-tools: A collection of tools to maintain vulnerability databases
# Copyright (C) 2016-  Delve Labs inc.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from lxml import etree
from datetime import datetime
import re
from openwebvulndb.common.logs import logger
import urllib

# %b = abbreviated month (Jan), %d = zero-padded day of month, %Y = year with century (2016), %I = hour in 12h format, %M = zero-padded minutes, %p = AM or PM.
securityfocus_date_format = "%b %d %Y %I:%M%p"


class InfoTabParser:
    """The parser for the info tab of a vulnerability entry in the security focus database.

    The info tab can contain the following data about a vulnerability:
    -Title (often takes the form of a short description)
    -Bugtraq ID (Security focus' ID system for vulnerability)
    -Class (type of vulnerability eg: Input validation error)
    -CVE ID (if it has one)
    -Remote (yes or no, if the vulnerability can be exploited remotely)
    -Local (see remote)
    -Publication date
    -Last update date
    -Credit
    -Vulnerable versions
    -not vulnerable versions
    """

    def __init__(self):
        self.html_tree = None
        
    def set_html_page(self, filename):
        parser = etree.HTMLParser()
        self.html_tree = etree.parse(filename, parser)

    def _parse_element(self, element_name):
        """Parse the elements in the info page that are contained in the <tr><td><span>element name</span></td><td>element
        value</td></tr> pattern. This is the pattern for all elements except the title.
        """
        element_value = self.html_tree.xpath('//span[text() = "' + element_name + '"]/../../td[2]/text()')
        # removes the white spaces around the value in the <td> (the whitespaces not preceded by a non-whitespace char
        # to preserve the white space between the word in the value.)
        element_value = element_value[0].strip()
        if len(element_value) == 0:
            return None
        else:
            return element_value

    def get_title(self):
        # return le text dans tous les elements span avec l'attribut class ayant la valeur "title"
        title = self.html_tree.xpath('//span[@class="title"]/text()')
        return title[0]
        
    def get_bugtraq_id(self):
        return self._parse_element("Bugtraq ID:")
        
    def get_vuln_class(self):
        return self._parse_element("Class:")
        
    def get_cve_id(self):
        # Get the td element with the cve id:
        td_element = self.html_tree.xpath('//span[text() = "' + "CVE:" + '"]/../../td[2]')
        td_element = td_element[0]
        cve = td_element.text.strip()
        if len(cve) == 0:
            return list()
        cve_ids = {cve}  # Use a set to remove duplicate cve ids.
        for br_tag in td_element:
            cve = br_tag.tail
            if cve is not None:
                cve = cve.strip()
                if len(cve) != 0:
                    cve_ids.add(cve)
        return list(cve_ids)
        
    def is_vuln_remote(self):
        return self._parse_element("Remote:")
        
    def is_vuln_local(self):
        return self._parse_element("Local:")
        
    def get_publication_date(self):
        string_date = self._parse_element("Published:")
        date = datetime.strptime(string_date, securityfocus_date_format)
        return date

    def get_last_update_date(self):
        string_date = self._parse_element("Updated:")
        date = datetime.strptime(string_date, securityfocus_date_format)
        return date
        
    def get_credit(self):
        return self._parse_element("Credit:")

    def get_vulnerable_versions(self):
        return self._get_version_list(True)

    def get_not_vulnerable_versions(self):
        return self._get_version_list(False)

    # FIXME precision about versions (like the Gentoo linux in wordpress_vuln_no_cve.html) are not parsed.
    def _get_version_list(self, get_vulnerable_versions):
        if get_vulnerable_versions:
            versions_list = self.html_tree.xpath('//span[text() = "Vulnerable:"]/../../td[2]/text()')
        else:
            versions_list = self.html_tree.xpath('//span[text() = "Not Vulnerable:"]/../../td[2]/text()')
        versions_list = [version.strip() for version in versions_list if len(version.strip()) > 0]
        return versions_list


class ReferenceTabParser:
    """The parser for the reference tab of vulnerability entry in the security focus database.

    The reference tab contains external references about the vulnerability. A reference is a description with an URL.
    """

    def __init__(self, url=None):
        self.html_tree = None
        self.url = url

    def set_html_page(self, filename):
        parser = etree.HTMLParser()
        self.html_tree = etree.parse(filename, parser)

    def _get_reference_parent_tag(self):
        return self.html_tree.xpath('//div[@id="vulnerability"]/ul')[0]  # returns the first ul tag in div vulnerability

    def _is_relative_url(self, url):
        return len(urllib.parse.urlparse(url).netloc) == 0

    def get_references(self):
        references_list = []
        parent_ul_tag = self._get_reference_parent_tag()
        for li in list(parent_ul_tag):  # create a list with all the li elements.
            a_tag = li[0]
            description = a_tag.text + a_tag.tail
            url = li.xpath('a/@href')[0]
            if self._is_relative_url(url) and self.url is not None:
                url = urllib.parse.urljoin(self.url, url)
            references_list.append({"description": description, "url": url})
        return references_list


class DiscussionTabParser:
    """The parser for the discussion tab of the vulnerability entry in the security focus database."""

    def __init__(self):
        self.html_tree = None

    def set_html_page(self, filename):
        parser = etree.HTMLParser()
        self.html_tree = etree.parse(filename, parser)

    def get_discussion(self):
        div_tag = self.html_tree.xpath('//div[@id="vulnerability"]')[0]  # The div that contains the discussion text.
        discussion_text = ""
        for br_tag in div_tag:  # the text of the discussion is contained after <br> tags in the div.
            if br_tag.tag == 'br':
                br_text = br_tag.tail
                if br_text is not None:
                    discussion_text += br_text
        return strip_whitespaces(discussion_text)


class ExploitTabParser:
    """The parser for the exploit tab of the vulnerability entry in the security focus database."""

    def __init__(self):
        self.html_tree = None

    def set_html_page(self, filename):
        parser = etree.HTMLParser()
        self.html_tree = etree.parse(filename, parser)

    def get_exploit_description(self):
        div_tag = self.html_tree.xpath('//div[@id="vulnerability"]')[0]  # the div that contains the exploit description
        exploit_description = ''
        for br_tag in div_tag:  # the description of the exploit is contained after <br> tags in the div.
            if br_tag.tag == 'br':
                text = br_tag.tail
                if text is not None:
                    if "Currently, we are not aware of any working exploits." in text:
                        return None
                    exploit_description += text
        return strip_whitespaces(exploit_description)


class SolutionTabParser:
    """The parser for the solution tab of the vulnerability entry in the security focus database."""

    def __init__(self):
        self.html_tree = None

    def set_html_page(self, filename):
        parser = etree.HTMLParser()
        self.html_tree = etree.parse(filename, parser)

    def get_solution(self):
        div_tag = self.html_tree.xpath('//div[@id="vulnerability"]')[0]  # The div that contains the text of the solution.
        solution_description = ''
        for br_tag in div_tag:  # the description of the solution is contained after <br> tags in the div.
            if br_tag.tag == 'br':
                text = br_tag.tail
                if text is not None:
                    if "Currently we are not aware of any" in text:
                        return None
                    solution_description += text
        return strip_whitespaces(solution_description)


def strip_whitespaces(string):
    """Replace multiple spaces, \n and \t with single space and remove leading and trailing space in the string. Return the stripped string"""
    stripped_string = re.sub('\s\s+', ' ', string)
    stripped_string = stripped_string.strip()
    return stripped_string
