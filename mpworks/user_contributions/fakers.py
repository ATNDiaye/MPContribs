from faker import Faker
import config

class CsvInputFile(object):
    """generate a fake mp-formatted csv input file for RecursiveParser"""
    def __init__(self):
        self.fake = Faker()
        self.section_titles = []

    def _get_level_n_section_line(
        self, n, mp_title_prob=25, comment_prob=50, max_comment_length=20
    ):
        """get an arbitrary level-n section line

        - format: ">*n TITLE/title # comment"
        - use one of config.mp_level01_titles a few times
        - only config.mp_level01_titles[0] is allowed to be level-0 title
        - append comment using config.csv_comment_char now and then
        - make level-0 titles all-caps
        """
        indentor = config.indent_symbol * (config.min_indent_level + n)
        allowed_level_titles = config.mp_level01_titles[:1 if n == 0 else None]
        title = self.fake.random_element(elements=allowed_level_titles) \
                if self.fake.boolean(
                    chance_of_getting_true=mp_title_prob
                ) and n < 2 else self.fake.word()
        self.section_titles.append(title)
        comment = self.fake.text(max_nb_chars=max_comment_length) \
                if self.fake.boolean(chance_of_getting_true=comment_prob) \
                else ''
        return ' '.join([
            indentor, title.upper() if n == 0 else title,
            config.csv_comment_char if comment != '' else '',
            comment
        ])

    def _make_level_n_section(self, n, max_level, max_num_subsec):
        """recursively generate nested level-n section
        
        - config.mp_level01_titles[1:] don't have subsections, all else can
        """
        print self._get_level_n_section_line(n)
        num_subsec = self.fake.random_int(max=max_num_subsec) \
                if n != max_level and \
                self.section_titles[-1] not in config.mp_level01_titles[1:] \
                else 0
        print "  --> num_subsec = ", num_subsec
        for i in range(num_subsec):
            self._make_level_n_section(n+1, max_level, max_num_subsec)
        # all subsections processed
        if num_subsec == 0:
            if self.section_titles[-1] == config.mp_level01_titles[1]:
                print '  ==> insert csv'
            else:
                print '  ==> insert key:value'
            if self.section_titles:
                self.section_titles.pop()

    def make_file(self, num_level0_sections=2, max_level=3):
        """produce a fake file structure"""
        # TODO: throw in comments at random places
        pass

