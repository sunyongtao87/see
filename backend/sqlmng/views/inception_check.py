#coding=utf8
from rest_framework.response import Response
from rest_framework.exceptions import ParseError
from utils.baseviews import BaseView
from sqlmng.mixins import PromptMxins, ActionMxins
from sqlmng.serializers import *
from sqlmng.models import *
import re

class InceptionCheckView(PromptMxins, ActionMxins, BaseView):
    '''
        查询：根据登录者身份返回相关的SQL，支持日期/模糊搜索。操作：执行（execute）, 回滚（rollback）,放弃（reject操作）
    '''
    queryset = Inceptsql.objects.all()
    serializer_class = InceptionSerializer
    serializer_step = StepSerializer
    action_type = '--enable-check'

    def check_forbidden_words(self, sql_content):
        forbidden_instance = ForbiddenWords.objects.first()
        if forbidden_instance:
            forbidden_word_list = [fword for fword in forbidden_instance.forbidden_words.split() if fword]
            forbidden_words = [fword for fword in forbidden_word_list if re.search(re.compile(fword, re.I), sql_content)]
            if forbidden_words:
                raise ParseError({self.forbidden_words: forbidden_words})

    def check_user_group(self, request):
        if request.data.get('env') == self.env_prd and not request.user.is_superuser:
            if not request.user.groups.exists():
                raise ParseError(self.not_exists_group)
            return request.user.groups.first().id

    def create_step(self, instance, users_id):
        if self.is_manual_review and instance.env == self.env_prd:
            instance_id = instance.id
            users_id.append(None)
            for index, uid in enumerate(users_id):
                status = 1 if index == 0 else 0
                step_serializer = self.serializer_step(data={'work_order':instance_id, 'user':uid, 'status':status})
                step_serializer.is_valid(raise_exception=True)
                step_serializer.save()

    def get_strategy_is_manual_review(self, env):
        strategy_instance = Strategy.objects.first()
        if not strategy_instance:
            return False
        return strategy_instance.is_manual_review if env == self.env_prd else False

    def create(self, request, *args, **kwargs):
        request_data = request.data
        request_data['group'] = self.check_user_group(request)
        request_data['treater'] = request_data.pop('treater_username')
        request_data['is_manual_review'] = self.get_strategy_is_manual_review(request_data.get('env'))
        serializer = self.serializer_class(data = request_data)
        serializer.is_valid(raise_exception = True)
        sql_content = request_data.get('sql_content')
        self.check_forbidden_words(sql_content)
        self.check_execute_sql(request_data.get('db'), sql_content)
        instance = serializer.save()
        self.create_step(instance, request_data['users'])
        self.mail(instance, self.action_type)
        return Response(self.ret)
