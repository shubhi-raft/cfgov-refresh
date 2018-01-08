import re

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.generic import TemplateView, View

import requests

from legacy.forms import HousingCounselorForm
from v1.s3utils import https_s3_url_prefix


class HousingCouncelorS3URLMixin(object):

    @staticmethod
    def s3_url(format, zipcode):
        path = settings.HOUSING_COUNSELOR_S3_PATH_TEMPLATE.format(
            format=format,
            zipcode=zipcode
        )
        return https_s3_url_prefix() + path

    @classmethod
    def s3_json_url(cls, zipcode):
        return cls.s3_url(format='json', zipcode=zipcode)

    @classmethod
    def s3_pdf_url(cls, zipcode):
        return cls.s3_url(format='pdf', zipcode=zipcode)


class HousingCounselorView(TemplateView, HousingCouncelorS3URLMixin):
    def get_template_names(self):
        if 'pdf' in self.request.GET:
            return 'hud/housing_counselor_pdf.html'
        else:
            return 'hud/housing_counselor.html'

    def get_context_data(self, **kwargs):
        context = super(HousingCounselorView, self).get_context_data(**kwargs)
        context['mapbox_access_token'] = settings.MAPBOX_ACCESS_TOKEN

        zipcode = self.request.GET.get('zipcode')
        context['zipcode'] = zipcode

        if zipcode:
            zipcode_valid = re.match(r'^\d{5}$', zipcode)

            if zipcode_valid:
                try:
                    api_json = self.get_counselors(self.request, zipcode)
                except requests.HTTPError:
                    pass
                else:
                    context.update({
                        'zipcode_valid': True,
                        'api_json': api_json,
                        'pdf_url': self.s3_pdf_url(zipcode),
                    })

        return context

    @classmethod
    def get_counselors(cls, request, zipcode):
        """Return list of housing counselors closest to a given zipcode.

        Raises requests.HTTPError on failure.
        """
        api_url = cls.s3_json_url(zipcode)

        response = requests.get(api_url)
        response.raise_for_status()

        return response.json()


class HousingCounselorPDFView(View, HousingCouncelorS3URLMixin):
    def get(self, request):
        form = HousingCounselorForm(request.GET)

        if not form.is_valid():
            return HttpResponseBadRequest('invalid zip code')

        zipcode = form.cleaned_data['zip']
        filename = '{}.pdf'.format(zipcode)

        s3_pdf_url = self.s3_pdf_url(zipcode)
        result = requests.get(s3_pdf_url)

        response = HttpResponse(result.content,
                                content_type='application/pdf')
        response['Content-Disposition'] = \
            'attachment; filename={0}'.format(filename)
        return response
