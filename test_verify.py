"""Offline tests for the identity check. Run them after you change a rule in verify.py:

    python -m unittest test_verify.py
"""
import unittest

from verify import _label, check_identity, company_matches, name_matches, pick, title_matches


def profile(name, company, link="", followers=0, url="https://www.linkedin.com/in/x/"):
    return {"name": name, "current_company_name": company, "followers": followers,
            "current_company": {"link": link} if link else None, "input": {"url": url}}


class LabelTest(unittest.TestCase):
    def test_country_code_domain(self):
        self.assertEqual(_label("acme.co.uk"), "acme")

    def test_plain_domain(self):
        self.assertEqual(_label("www.vercel.com"), "vercel")


class NameTest(unittest.TestCase):
    def test_exact_name(self):
        self.assertTrue(name_matches("Paul", "Copplestone", "Paul Copplestone"))

    def test_middle_name_on_profile(self):
        self.assertTrue(name_matches("Victor", "Braga", "Victor Urano Braga"))

    def test_nickname_does_not_match_full_first_name(self):
        self.assertFalse(name_matches("Jake", "Diamond-Reivich", "Jacob Diamond-Reivich"))


class CompanyTest(unittest.TestCase):
    def test_company_page_website(self):
        self.assertTrue(company_matches("composio.dev", "composio.dev", "Composio"))

    def test_name_used_when_website_is_a_short_link(self):
        self.assertTrue(company_matches("figma.com", "bit.ly", "Figma, Inc."))

    def test_name_inside_domain(self):
        self.assertTrue(company_matches("makenotion.com", None, "Notion"))

    def test_name_with_extra_words(self):
        self.assertTrue(company_matches("acme.com", None, "Acme Group"))

    def test_whole_word_only(self):
        self.assertFalse(company_matches("meta.com", None, "Metabase"))

    def test_generic_name_is_not_evidence(self):
        self.assertFalse(company_matches("your-company.com", None, "Company"))


class TitleTest(unittest.TestCase):
    def test_role_in_search_title(self):
        title = "Ivan Zhao - Founder at Notion"
        self.assertTrue(title_matches("notion.so", "Notion", title, "Ivan Zhao"))

    def test_former_role_does_not_count(self):
        title = "Ivan Zhao - Former founder at Notion"
        self.assertFalse(title_matches("notion.so", "Notion", title, "Ivan Zhao"))

    def test_lead_own_name_does_not_count(self):
        self.assertFalse(title_matches("vercel.com", "Vercel", "Vercel Smith - Engineer at Acme",
                                       "Vercel Smith"))

    def test_short_company_name_does_not_count(self):
        self.assertFalse(title_matches("ab.com", "AB", "John Doe - CEO at AB", "John Doe"))


class CheckIdentityTest(unittest.TestCase):
    lead = {"first": "Guillermo", "last": "Rauch", "email": "g@vercel.com", "company": "Vercel"}
    vercel = {"website_simplified": "vercel.com"}

    def test_verified(self):
        p = profile("Guillermo Rauch", "Vercel", "https://www.linkedin.com/company/vercel")
        self.assertEqual(check_identity(self.lead, p, self.vercel), "verified")

    def test_job_change(self):
        link = "https://www.linkedin.com/company/superlogical"
        p = profile("Guillermo Rauch", "Superlogical", link)
        company = {"website_simplified": "superlogical.com"}
        self.assertEqual(check_identity(self.lead, p, company), "job_change")

    def test_personal_email_is_unverified(self):
        lead = dict(self.lead, email="g@gmail.com")
        p = profile("Guillermo Rauch", "Vercel", "https://www.linkedin.com/company/vercel")
        self.assertEqual(check_identity(lead, p, self.vercel), "unverified")

    def test_different_name_is_no_match(self):
        p = profile("Lee Robinson", "Vercel", "https://www.linkedin.com/company/vercel")
        self.assertEqual(check_identity(self.lead, p, self.vercel), "no_match")


class PickTest(unittest.TestCase):
    def test_more_followers_wins_between_two_verified_profiles(self):
        lead = {"first": "Guillermo", "last": "Rauch", "email": "g@vercel.com", "company": "Vercel"}
        link = "https://www.linkedin.com/company/vercel"
        small = profile("Guillermo Rauch", "Vercel", link, 122, "https://linkedin.com/in/a/")
        large = profile("Guillermo Rauch", "Vercel", link, 70826, "https://linkedin.com/in/b/")
        companies = {"vercel": {"website_simplified": "vercel.com"}}
        result, chosen = pick(lead, [small, large], companies)
        self.assertEqual(result, "verified")
        self.assertEqual(chosen["input"]["url"], "https://linkedin.com/in/b/")


if __name__ == "__main__":
    unittest.main()
