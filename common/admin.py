from bs4 import BeautifulSoup


class StripDivMixin:
    def strip_outer_div(self, field):
        # if the entire content is wrapped in a single <div>, unwrap it
        field_data = self.cleaned_data[field]
        soup = BeautifulSoup(field_data, "html.parser")

        if len(soup.contents) == 1 and soup.contents[0].name == "div":
            soup.contents[0].unwrap()

        return str(soup).strip()
