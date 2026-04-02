from django import forms


class OTPVerifyForm(forms.Form):
    otp_code = forms.CharField(min_length=6, max_length=6)
