# encoding: utf-8
import logging
import threading
from PyQt4.QtGui import *
from PyQt4.QtCore import *
import sys
import time
from gui.misc import LoggerHandler, ParameterSet, _THREAD_AMOUNT_SAFE
from reaper.misc import take
from reaper.constants import REQUIRED_SUFFIXES, AUTO
from reaper.content_man import ContentManager
from reaper.grab import start_multi_threading
from reaper.id_gen import get_ids



class Form(QDialog, object):

    _CheckBox_keyword_names = map(lambda item: 'cb_' + item, ['company', 'factory', 'corp', 'center', 'inst'])
    _LineEdit_names = map(lambda item: 'le_' + item, ['start_id', 'end_id', 'from_page', 'to_page', 'thread_amount'])

    def __init__(self, transactor_func, parameters=None, parent=None):
        super(Form, self).__init__(parent, )

        self.resize(640, 400)

        self.logger_widget = QTextBrowser()
        self.logger_widget.setFocusPolicy(Qt.NoFocus)

        self.btn_start = QPushButton(u'开始')
        self.btn_start.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))

        layout = QVBoxLayout()
        layout.addLayout(self._gen_LineEdit_layout())
        layout.addLayout(self._gen_CheckBox_layout())
        layout.addWidget(self.logger_widget)
        self.setLayout(layout)

        logging.basicConfig(
            format='',
        )

        self.logger = logging.getLogger(__name__)
        handler = LoggerHandler(self.logger_widget)
        handler.setFormatter(logging.Formatter(
            fmt='<font color=blue>%(asctime)s</font> <font color=red><b>%(levelname) 8s</b></font> %(message)s',
            datefmt='%m/%dT%H:%M:%S'
        ))
        self.logger.addHandler(handler)

        self.connect(self.btn_start, SIGNAL('clicked()'), self.btn_start_click)
        self.connect(self.logger_widget, SIGNAL('newLog(QString)'), self.new_log)
        self.connect(self, SIGNAL('jobFinished()'), self.grabbing_finished)

        self.parameters = parameters

        self.transactor_func = transactor_func


    def _gen_LineEdit_layout(self):
        h_layout = QHBoxLayout()

        def _gen_layout(label, attribute, max_length=6, default='000000'):
            _layout = QHBoxLayout()

            line_edit = QLineEdit()
            line_edit.setText(default)
            line_edit.setFixedSize(max_length * 10, 20)
            line_edit.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed))
            line_edit.setAlignment(Qt.AlignRight)
            line_edit.setMaxLength(max_length)

            _layout.addWidget(QLabel(label))
            _layout.addWidget(line_edit)

            self.__setattr__(attribute, line_edit)

            return _layout

        h_layout.addStretch()
        h_layout.addWidget(QLabel(u'<font color="red"><b>搜企爬虫</b></font>'))
        h_layout.addStretch()
        h_layout.addWidget(self.btn_start)
        h_layout.addStretch()

        for args in zip((u'起始id:', u'结束id:', u'起始页:', u'结束页:', u'线程数:'),
                        Form._LineEdit_names,
                        (6, 6, 3, 3, 3),
                        ('000000', '999999', '1', '', '')):
            h_layout.addLayout(apply(_gen_layout, args))
            h_layout.addStretch()

        return h_layout


    def _gen_CheckBox_layout(self):
        h_layout = QHBoxLayout()

        h_layout.addWidget(QLabel(u'关键词:'))
        for attr, item in zip(
            Form._CheckBox_keyword_names,
            map(lambda item: item.decode('utf-8'), REQUIRED_SUFFIXES)
        ):
            checkbox = QCheckBox(item)
            checkbox.setChecked(True)
            self.__setattr__(attr, checkbox)
            h_layout.addWidget(checkbox)

        h_layout.addStretch()
        h_layout.addWidget(QLabel(u'若<font color="red">结束页</font>与<font color="red">线程数</font>留空，则自动设置之'))

        return h_layout


    def grabbing_finished(self):
        self.logger_widget.append('<b><font color="green">job %s done</font></b>' % self._param)


    def new_log(self, s):
        self.logger_widget.append(s)


    def get_checked_keywords(self):
        return filter(
            lambda item: item.checkState() == Qt.Checked,
            map(
                lambda item: self.__getattribute__(item),
                Form._CheckBox_keyword_names
            )
        )


    def start_threads(self, parameters):
        self.logger.debug('starting threads')
        def _(params):
            cont_man = ContentManager(self.transactor_func)
            for param in params:
                self.logger.info(
                    'keyword %s, city %s, (%d, %d) starting',
                    param.keyword, param.city_id,
                    param.from_page, param.to_page
                )

                start_multi_threading(
                    param.keyword,
                    (param.from_page, param.to_page),
                    city_code=param.city_id,
                    content_man=cont_man,
                    max_retry=15,
                    logger=self.logger
                )

            cont_man.join_all()

            self.emit(SIGNAL('jobFinished()'))

        # FIXME problem: I/O operation on closed file`, probable solution: use external func
        for sub_params in take(parameters, by=len(parameters) / _THREAD_AMOUNT_SAFE):
            transactor_thread = threading.Thread(target=_, args=(sub_params,))
            transactor_thread.setDaemon(True)
            transactor_thread.start()


    def prepare_parameters(self):
        def _prepare_parameters(start_id, end_id, from_page, to_page, checked_keywords):
            params = []
            for city_id in get_ids(start_id, end_id):
                for keyword in checked_keywords:
                    params.append(ParameterSet(keyword, (from_page, to_page), city_id))

            return params

        (start_id, end_id,
        from_page, to_page,
        self.thread_amount) = map(
            lambda widget_name: unicode(self.__getattribute__(widget_name).text()),
            Form._LineEdit_names
        )
        if not (start_id and end_id and from_page):
            self.logger.error('请输入有效的值')
            return

        if not to_page: # TODO implement auto to_page mechanism
            to_page = AUTO
        if not self.thread_amount: # TODO implement auto thread_amount mechanism
            self.thread_amount = AUTO

        self.logger.debug(
            'start_id: %s, end_id: %s, from_page: %s, to_page: %s, thread_amount: %s',
            start_id, end_id,
            from_page, to_page,
            self.thread_amount
        )

        return _prepare_parameters(
            start_id, end_id, int(from_page), int(to_page),
            map(lambda item: unicode(item.text()).encode('utf-8'), self.get_checked_keywords()))


    def has_validate_inputs(self):
        _get_texts = lambda iterable: map(lambda _: unicode(self.__getattribute__(_).text()), iterable)

        start_id, end_id = _get_texts(('le_start_id', 'le_end_id'))
        if any(map(lambda _: not (_.isdigit() and len(_) == 6), (start_id, end_id))):
            self.logger.error('起始id和结束id必须为六位整数')
            return False
        if start_id > end_id:
            self.logger.error('起始id必须小于等于结束id')
            return False

        from_page, to_page = _get_texts(('le_from_page', 'le_to_page'))
        if from_page.isdigit():
            if to_page.isdigit():
                if from_page > to_page:
                    self.logger.error('起始页必须小于等于结束页')
                    return False
            elif to_page and not to_page.isdigit():
                self.logger.error('结束页必须为小于三位的整数')
                return False
        else:
            self.logger.error('起始页必须为小于三位的整数')
            return False

        return True


    def btn_start_click(self):
        self.logger.debug(
            '%s checked',
            ' '.join(map(lambda item: unicode(item.text()).encode('utf-8'), self.get_checked_keywords())))

        if not self.has_validate_inputs():
            return

        self.start_threads(self.prepare_parameters())


# TODO implement config file mechanism
if __name__ == '__main__':
    the_the_lock = threading.RLock()
    # with open(str(int(time.time() * 100)) + '.txt', 'w') as ff:
    with the_the_lock:
        def transact(item):
            the_lock = threading.RLock()
            if not item.is_valid_item():
                return
            with the_lock:
                # print >> ff, item.corp_name, ',', item.website_title, ',', item.introduction
                # ff.flush()
                pass


        app = QApplication(sys.argv)
        form = Form(transact)
        form.show()
        app.exec_()


