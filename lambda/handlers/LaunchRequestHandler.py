import logging
import ask_sdk_core.utils as ask_utils

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import ui
from ask_sdk_model import Response
from shopinfo import ReputationSearchApiParameter,GeoLocation,SearchRange,ApiRequestParameter,ReputationInfo

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 位置情報の共有を許可するように促すカードをAlexaアプリへ表示する関数の引数
permissions = ["alexa::devices:all:geolocation:read"]

# Alexaアプリのカードや画面付きデバイスへ表示するタイトル
card_title = "紹介したお店と現在地からの距離"

# 探したいメニュー
search_menu = 'ラーメン'

# 検索範囲 緯度/経度からの検索範囲(半径) 1:300m、2:500m、3:1000m、4:2000m、5:3000m
search_range = 4

# 一度の発話で紹介する口コミの数
referrals_at_once = 2

# カードに表示する店名一覧
# 一度にすべての店舗を表示するのでグローバル変数にした
shop_name = ''

class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for Skill Launch."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool

        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        global shop_name
        # type: (HandlerInput) -> Response     
        # デバイスが位置情報取得に対応しているか、Alexaアプリが位置情報の共有を許可しているかチェック
        context = handler_input.request_envelope.context
        isgeosupported = context.system.device.supported_interfaces.geolocation
        geo_object = context.geolocation
        if isgeosupported is None or geo_object is None:
            speak_output = "このスキルは、位置情報を使用します。\
                位置情報の共有を有効にするには、Alexaアプリに移動し、権限を有効にしてください。\
                なお、固定デバイスの場合は位置情報を取得するようには設定されていないため、このスキルはお使いになれません。"
            
            return (
                handler_input.response_builder
                .speak(speak_output)
                .response
            )

        # APIのリクエストパラメータ作成
        api = ReputationSearchApiParameter()

        menu = api.search_by_menu(search_menu)

        latitude = context.geolocation.coordinate.latitude_in_degrees
        longitude = context.geolocation.coordinate.longitude_in_degrees
        geolocation = GeoLocation.set(latitude, longitude)

        radius = SearchRange.set(search_range) # 2000m

        parameter = ApiRequestParameter.merge(menu, geolocation, radius)

        # APIレスポンス
        url = api.url
        api_response = ReputationInfo(url, parameter)
        return_code = api_response.return_code()

        if return_code == 200: # 検索でお店がヒットしたら
            shop_reputation = api_response.reputation_search()
            hitcount = api_response.total_hits
            speak_output = f"{hitcount}件の口コミが見つかりました。"

            session_attr = handler_input.attributes_manager.session_attributes
            session_attr['shopinfo'] = shop_reputation
            session_attr['remaining_reputations'] = len(shop_reputation)
            session_attr['shop_index_begin'] = 0
        else:
            speak_output = 'すみません。お店の口コミは見つかりませんでした。'
            return (handler_input.response_builder.speak(speak_output).response)

        if session_attr['remaining_reputations'] <= referrals_at_once:
            session_attr['next_pages'] = 'no'

            for i in range(session_attr['remaining_reputations']):
                shop_name     = '・' + shop_reputation[i]['name'] \
                                + '(' + str(shop_reputation[i]['distance']) + 'm)' + '\n'
                speak_output += shop_reputation[i]['kana'] + '。' \
                                + shop_reputation[i]['comment'] \
                                + 'お店まではここから約' + str(shop_reputation[i]['distance']) + 'メートルです。'

            speak_output += '口コミは以上です。'

            return (
                handler_input.response_builder
                .speak(speak_output)
                .set_card(ui.StandardCard(title=card_title,text=shop_name))
                .response
                )
        else:
            speak_output += 'いくつかをご紹介します。'
            # お店の一覧を画面へ表示する
            for i in range(session_attr['remaining_reputations']):
                shop_name    += '・' + shop_reputation[i]['name'] \
                                + '(' + str(shop_reputation[i]['distance']) + 'm)' + '\n'

            # 一回の発話でお知らせするお店
            for i in range(referrals_at_once):
                speak_output += shop_reputation[i]['kana'] + '。' \
                                + shop_reputation[i]['comment'] \
                                + 'お店まではここから約' + str(shop_reputation[i]['distance']) + 'メートルです。' \
                
                session_attr['next_pages'] = 'yes'
                session_attr['shop_index_begin'] += 1

            session_attr['shop_index_end'] = session_attr['shop_index_begin'] + referrals_at_once
            session_attr['remaining_reputations'] -= referrals_at_once
            speak_output += "次の口コミを聞きますか？"

            session_attr['repeat_speakoutput'] = speak_output 

            ask_output = "そのほかの口コミを聞きますか？"

            return (
                handler_input.response_builder
                .speak(speak_output)
                .set_card(ui.StandardCard(title=card_title,text=shop_name))
                .ask(ask_output)
                .set_should_end_session(False)
                .response
                )