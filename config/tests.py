from django.test import SimpleTestCase

class ProjectSmokeTest(SimpleTestCase):
    def test_admin_url_redirects_to_login(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
