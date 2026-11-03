from django import forms


class LoginForm(forms.Form):
    identifier = forms.CharField(
        label="Email, username or roll number",
        max_length=254,
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "username"}
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "current-password"}
        ),
    )
