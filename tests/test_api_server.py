"""
Unit and integration tests for LinkedIn Profile Viewer REST API server and scrapers.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

import api_server
from api_server import app
from linkedin_profile_viewer.models import Person, Experience, Education


class TestAPIServer(unittest.TestCase):

    def setUp(self):
        api_server.API_KEY = "test-api-key"
        self.client = TestClient(app)
        self.headers = {"X-API-Key": "test-api-key"}

    def test_health_check(self):
        """Test healthcheck endpoint."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data.get("status"), "healthy")

    def test_scrape_requires_api_key(self):
        """Public deployment still requires the application API key."""
        response = self.client.get(
            "/api/profileinfo?profileUrl=https://www.linkedin.com/in/test/"
        )
        self.assertEqual(response.status_code, 401)

    @patch("api_server._scrape_profile")
    def test_get_profile_info_v1(self, mock_scrape):
        """Test v1 DOM endpoint."""
        mock_scrape.return_value = {
            "status": "success",
            "data": Person(
                linkedin_url="https://www.linkedin.com/in/test/",
                name="Test User",
                headline="Software Engineer",
            ).to_dict()
        }
        response = self.client.get("/api/profileinfo?profileUrl=https://www.linkedin.com/in/test/", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["name"], "Test User")

    @patch("api_server._scrape_profile_vision")
    def test_get_profile_info_v2_vision(self, mock_scrape_vision):
        """Test v2 Vision AI endpoint."""
        mock_scrape_vision.return_value = {
            "status": "success",
            "data": Person(
                linkedin_url="https://www.linkedin.com/in/test/",
                name="Vision User",
                headline="AI Researcher",
            ).to_dict()
        }
        response = self.client.get("/api/v2/profileinfo?profileUrl=https://www.linkedin.com/in/test/", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["name"], "Vision User")

    @patch("api_server._scrape_profile_ocr")
    def test_get_profile_info_v3_ocr(self, mock_scrape_ocr):
        """Test v3 Local OCR endpoint."""
        mock_scrape_ocr.return_value = {
            "status": "success",
            "data": Person(
                linkedin_url="https://www.linkedin.com/in/test/",
                name="OCR User",
                headline="Data Scientist",
            ).to_dict()
        }
        response = self.client.get("/api/v3/profileinfo?profileUrl=https://www.linkedin.com/in/test/", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["name"], "OCR User")


if __name__ == "__main__":
    unittest.main()
