from datetime import timedelta

from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.test import TestCase
from django.utils import timezone

from wagtail.core.models import Site

from mock import patch
from model_bakery import baker

from jobmanager.models.django import (
    ApplicantType, City, Grade, JobCategory, Office, Region, State
)
from jobmanager.models.pages import JobListingPage
from jobmanager.models.panels import GradePanel, USAJobsApplicationLink
from v1.models.snippets import ReusableText
from v1.tests.wagtail_pages.helpers import save_new_page


class JobListingPageQuerySetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.now().date()
        root_page = Site.objects.get(is_default_site=True).root_page

        division = JobCategory.objects.create(job_category='Division')
        location = Region.objects.create(abbreviation='NW', name='Northwest')

        defaults = {
            'description': 'description',
            'salary_min': 0,
            'salary_max': 1000,
            'division': division,
            'location': location,
        }

        live_job = JobListingPage(
            title='Job',
            open_date=today - timedelta(days=7),
            close_date=today + timedelta(days=7),
            **defaults
        )
        root_page.add_child(instance=live_job)

        another_live_job = JobListingPage(
            title='Another job',
            open_date=today - timedelta(days=7),
            close_date=today + timedelta(days=7),
            **defaults
        )
        root_page.add_child(instance=another_live_job)

        expired_job = JobListingPage(
            title='Expired job',
            open_date=today - timedelta(days=7),
            close_date=today - timedelta(days=1),
            **defaults
        )
        root_page.add_child(instance=expired_job)

    def test_open(self):
        open_jobs = JobListingPage.objects.open()
        self.assertEqual(open_jobs.count(), 2)
        self.assertSequenceEqual(
            open_jobs.values_list('title', flat=True),
            ['Another job', 'Job']
        )


class JobListingPageTestCase(TestCase):
    def setUp(self):
        self.division = baker.make(JobCategory)
        self.location = baker.make(Region)

        page_clean = patch('jobmanager.models.pages.CFGOVPage.clean')
        page_clean.start()
        self.addCleanup(page_clean.stop)

    def prepare_job_listing_page(self, **kwargs):
        kwargs.setdefault('description', 'default')
        kwargs.setdefault('division', self.division)
        kwargs.setdefault('location', self.location)
        return baker.prepare(JobListingPage, **kwargs)

    def test_clean_with_all_fields_passes_validation(self):
        page = self.prepare_job_listing_page()
        try:
            page.full_clean()
        except ValidationError:  # pragma: nocover
            self.fail('clean with all fields should validate')

    def test_clean_without_description_fails_validation(self):
        page = self.prepare_job_listing_page(description=None)
        with self.assertRaises(ValidationError):
            page.full_clean()

    def test_clean_without_open_date_fails_validation(self):
        page = self.prepare_job_listing_page(open_date=None)
        with self.assertRaises(ValidationError):
            page.full_clean()

    def test_clean_without_close_date_fails_validation(self):
        page = self.prepare_job_listing_page(close_date=None)
        with self.assertRaises(ValidationError):
            page.full_clean()

    def test_clean_without_salary_min_fails_validation(self):
        page = self.prepare_job_listing_page(salary_min=None)
        with self.assertRaises(ValidationError):
            page.full_clean()

    def test_clean_without_salary_max_fails_validation(self):
        page = self.prepare_job_listing_page(salary_max=None)
        with self.assertRaises(ValidationError):
            page.full_clean()

    def test_clean_without_division_fails_validation(self):
        page = self.prepare_job_listing_page(division=None)
        with self.assertRaises(ValidationError):
            page.full_clean()

    def make_page_with_grades(self, *grades):
        page = self.prepare_job_listing_page()
        save_new_page(page)

        for grade in grades:
            panel = GradePanel.objects.create(
                grade=baker.make(Grade, grade=str(grade)),
                job_listing=page
            )
            page.grades.add(panel)

        return page

    def test_ordered_grades(self):
        page = self.make_page_with_grades('3', '2', '1')
        self.assertEqual(page.ordered_grades, ['1', '2', '3'])

    def test_ordered_grades_removes_duplicates(self):
        page = self.make_page_with_grades('3', '2', '2', '2', '1', '1')
        self.assertEqual(page.ordered_grades, ['1', '2', '3'])

    def test_ordered_grades_sorts_numerically(self):
        page = self.make_page_with_grades('100', '10', '11', '1')
        self.assertEqual(page.ordered_grades, ['1', '10', '11', '100'])

    def test_ordered_grades_non_numeric_after_numeric(self):
        page = self.make_page_with_grades('2', '1', 'b', 'B', 'a', 'A')
        self.assertEqual(page.ordered_grades, ['1', '2', 'A', 'B', 'a', 'b'])

    def test_ordered_grades_returns_strings(self):
        page = self.make_page_with_grades('3', '2', '1')
        for grade in page.ordered_grades:
            self.assertIsInstance(grade, str)

    def test_context_for_page_with_region_location(self):
        region = baker.make(
            Region,
            name="Tri-State Area",
            abbreviation="TA",
        )
        state = baker.make(
            State,
            name="Unknown",
            abbreviation='UN',
            region=region
        )
        cities = ['Danville', 'Townsville']
        for city in cities:
            region.cities.add(
                City(name=city, state=state)
            )
        page = self.prepare_job_listing_page(location=region)
        test_context = page.get_context(HttpRequest())
        self.assertEqual(len(test_context['states']), 1)
        self.assertEqual(test_context['states'][0], state.abbreviation)
        self.assertEqual(len(test_context['cities']), 2)
        self.assertIn(test_context['cities'][0].name, cities)

    def test_context_for_page_with_office_location(self):
        region = baker.make(
            Region,
            name="Mideastern",
            abbreviation="ME")
        office = baker.make(
            Office,
            name="Zenith Office",
            abbreviation="ZE")
        state = baker.make(
            State,
            name="Winnemac",
            abbreviation='WM',
            region=region
        )
        office.cities.add(
            City(name='Zenith', state=state)
        )
        page = self.prepare_job_listing_page(location=office)
        test_context = page.get_context(HttpRequest())
        self.assertEqual(len(test_context['states']), 0)
        self.assertEqual(len(test_context['cities']), 1)
        self.assertEqual(test_context['cities'][0].name, 'Zenith')

    def test_context_without_about_us_snippet(self):
        page = self.prepare_job_listing_page()
        test_context = page.get_context(HttpRequest())
        self.assertNotIn('about_us', test_context)

    def test_context_with_about_us_snippet(self):
        about_us_snippet = ReusableText(title='About us (For consumers)')
        about_us_snippet.save()
        page = self.prepare_job_listing_page()
        test_context = page.get_context(HttpRequest())
        self.assertIn('about_us', test_context)
        self.assertEqual(
            test_context['about_us'],
            about_us_snippet
        )

    def test_usajobs_application_link_ordering(self):
        page = self.prepare_job_listing_page()
        save_new_page(page)

        page.usajobs_application_links = [
            USAJobsApplicationLink(
                announcement_number='1',
                applicant_type=baker.make(ApplicantType, applicant_type='1'),
            ),
            USAJobsApplicationLink(
                announcement_number='2',
                applicant_type=baker.make(ApplicantType, applicant_type='2'),
            ),
        ]

        result = page.usajobs_application_links.order_by('applicant_type')
        self.assertEqual(result.first().announcement_number, '1')
