"""iter127의 원문을 직접 읽은 후보별 판정. 범용 임상 라벨 추출기가 아니다."""
import json
import time
from mr127_select import OUT, read, save, sha

# patient|decision|polarity|target_conflict|literal report quote|판단 근거
TABLE = r'''14670|include|positive|0|the third and bilateral lateral ventricles are dilated secondary to atrophy.|양측 측뇌실 확장 명시. 위축이라는 원인 설명은 존재 불확실성이 아니다.
14967|include|positive|0|Sulcal distances, lateral ventricles, third ventricle widths, and Sylvian fissures have become prominent secondary to volume loss|복수 측뇌실의 prominence와 volume loss 명시. 경도 위축도 유지한다.
17182|unknown|unknown|0|Lateral ventricle and third ventricle are mildly prominent|단수 lateral ventricle이며 양측 범위 불명.
3405|include|positive|0|the bilateral lateral ventricles and third ventricle are slightly enlarged.|양측 측뇌실의 경도 확장 명시. 전이의 시간 비교는 목표 크기 판정과 별개.
14550|include|positive|0|Lateral and third ventricles and sulci are mildly enlarged (mild cerebral atrophy).|복수 측뇌실 경도 확장. CSF resorption 원인 추정은 확장 존재의 hedge가 아니다.
1967|include|positive|0|Bilateral lateral ventricles and third ventricle are wide|양측 측뇌실 폭 증가 명시. 전이·혈액소견의 불확실성은 별개.
18291|include|positive|0|Bilateral lateral ventricles, third ventricle are mildly prominent.|양측 측뇌실 prominence 명시. 골수종 동반을 제외하지 않는다.
17804|include|positive|0|The 3rd and lateral ventricles and sulci are mildly enlarged consistent with patient age.|복수 측뇌실 확장 명시. 나이와의 일치 설명은 음성 근거가 아니다. 운동 artifact 기록을 유지한다.
15758|include|positive|0|Both lateral ventricles and 3rd ventricle are widened secondary to atrophy|양측 폭 증가와 좌우 수치 명시. 위축 관련 확장 포함.
14950|include|positive|0|Sulcal spaces, lateral ventricles, and third ventricle widths, and Sylvian fissures are prominent secondary to volume loss|복수 측뇌실 prominence 명시. mild senile atrophy 포함.
16645|exclude|unilateral|0|The left lateral ventricle, particularly the temporal horn, is observed to be dilated|좌측만 확장. 양측 대상으로 확장하지 않는다.
17759|include|positive|0|Bilateral lateral ventricles and third ventricle are enlarged.|양측 확장 명시. NPH 원인 판단은 평가하지 않는다.
15831|unknown|unknown|1|The ventricular system is of normal width.|전체 정상 폭과 우측 비대칭 확장 병기. 양측 확장도 미확인.
16126|exclude|unilateral|0|Mild enlargement is present in the right lateral ventricle atrium|우측 atrium만 확장. choroid cyst 추정과 별개로 양측 미확인.
14770|include|positive|0|The third and lateral ventricles and sulci are widened due to cerebral volume loss.|복수 측뇌실 확장 명시. 저산소성 edema는 별도 동반소견.
17564|include|positive|0|Enlargement compatible with atrophy has been observed in the 3rd ventricle, both lateral ventricles|양측 측뇌실 확장 명시. metastasis 치료 변화 문맥과 목표 정답을 구분.
14766|exclude|not_positive|0|More prominent narrowing is observed in the occipital horn of the right lateral ventricle.|mass effect로 우측 narrowing. 후보 확장 극성과 불일치.
15179|include|positive|0|Convexity sulci, basal cisterns, sylvian fissures and both lateral ventricles are dilated|양측 측뇌실 확장 명시. chronic infarct 동반.
7790|include|positive|0|Bilateral lateral ventricles and third ventricle are mildly prominent.|양측 경도 prominence 명시. 병변 원인 추정은 목표 존재와 별개.
16347|include|positive|0|the 3rd and lateral ventricles are observed to be midline and dilated.|복수 측뇌실 확장 명시. 정상 gray matter/sulci 문장은 측뇌실 정상 폭 주장이 아니다.
16576|include|negative|0|the 3rd and lateral ventricles are midline and of normal width.|복수 측뇌실 정상 폭 명시. 소뇌 고신호와 목표 크기는 별개.
17117|include|negative|0|The width of the 3rd and lateral ventricles and hemispheric sulci is normal.|복수 측뇌실 정상 폭 명시.
16714|unknown|unknown|0|Bilateral lateral ventricles are normal.|일반 normal만 있어 명시적 크기·폭/확장 부재를 인증 못 함.
16713|unknown|unknown|0|Bilateral lateral ventricles are normal.|일반 normal만 있어 명시적 크기·폭/확장 부재를 인증 못 함.
16246|unknown|unknown|0|The third ventricle and lateral ventricular system are in normal location and of size compatible with age.|정상은 location의 수식어. 크기는 age-compatible이며 정상 크기/비확장으로 보충하지 않는다.
17201|include|negative|0|The width of the third and lateral ventricles and hemispheric sulci is normal.|복수 측뇌실 정상 폭 명시. hippocampal cyst는 별개.
16623|include|negative|0|Third and both lateral ventricles are midline and of normal width.|양측 측뇌실 정상 폭 명시.
17856|unknown|unknown|0|Third and lateral ventricles and sulci are normal.|일반 정상만 있으며 목표 정상 크기·폭 미확인.
16764|include|negative|0|the third and lateral ventricles are midline and of normal size.|복수 측뇌실 정상 크기 명시. optic sheath 확장은 목표와 다른 구조.
16614|include|negative|0|the third and lateral ventricles are midline and of normal size.|복수 측뇌실 정상 크기 명시.
17185|include|negative|0|The width of the 3rd and lateral ventricles and hemispheric sulci is normal.|복수 측뇌실 정상 폭. cervical findings는 별개.
16463|include|negative|0|Third and both lateral ventricles are midline and of normal width.|양측 측뇌실 정상 폭. gliosis 동반은 별개.
10914|include|negative|0|the third and lateral ventricles are midline and of normal width.|복수 측뇌실 정상 폭.
16451|include|negative|0|Third and both lateral ventricles are midline and of normal width.|양측 정상 폭. mastoiditis를 이유로 제외하지 않는다.
15764|include|negative|0|the third and lateral ventricles are midline and of normal size.|복수 정상 크기. otitis·sinusitis는 별개.
15453|unknown|unknown|0|Third ventricle and lateral ventricles, widths of hemispheric cortical sulci are within normal limits.|widths가 sulci에만 붙어 측뇌실은 일반 정상인지 수식 범위 모호. 원 기준대로 unknown.
16029|unknown|unknown|0|The 3rd ventricle and lateral ventricular system are in normal location and width compatible with age.|정상 location과 age-compatible width를 정상 폭/확장 부재로 확대하지 않는다.
15264|unknown|unknown|0|The third ventricle and lateral ventricles, and the widths of the hemispheric cortical sulci are within normal limits.|측뇌실은 일반 정상 기술, widths는 sulci의 수식. 목표 명시적 크기 근거 미확인.
17327|include|negative|0|Lateral ventricles, third and fourth ventricle sizes are normal.|복수 측뇌실 sizes 정상 명시.
17508|unknown|unknown|0|Lateral ventricle and third ventricle widths are normal.|단수 lateral ventricle. 양측 명시적 정상 폭을 추정하지 않는다.
16748|include|negative|0|the 3rd and lateral ventricles are midline and of normal size.|복수 측뇌실 정상 크기. optic nerve CSF prominence는 다른 대상.
15999|unknown|unknown|0|Third ventricle and lateral ventricular system are in normal location and of width consistent with age.|정상 location과 나이에 따른 width 설명. 확장 부재/정상 폭으로 채우지 않는다.
16928|include|negative|0|Width of third and lateral ventricles and hemispheric sulci is normal.|복수 정상 폭. 얼굴·목의 감염 추정은 별개.
16567|include|negative|0|the 3rd and lateral ventricles are midline and of normal width.|복수 정상 폭. gliotic foci 동반 유지.
15614|include|negative|0|the third and lateral ventricles are midline and of normal width.|복수 정상 폭. cortical atrophy·운동 artifact는 크기 정답 상충이 아니다. 후순위 검토만이며 선정 cutoff 이후.
18263|include|negative|0|The width of the third and lateral ventricles and hemispheric sulci is normal.|복수 정상 폭. 후순위 검토만이며 선정 cutoff 이후.
36505|include|negative|0|The width of the third and lateral ventricles and hemispheric sulci is normal.|복수 정상 폭. pituitary hypertrophy 대상은 별개.
353|include|negative|0|The third ventricle, both lateral ventricles, and sulci are of normal caliber.|양측 정상 caliber 명시.
70814|include|negative|0|Third ventricle, bilateral lateral ventricles, and sulci are of normal width.|양측 정상 폭 명시.
68800|include|negative|0|The third ventricle and both lateral ventricles are of normal size.|양측 정상 크기. age-compatible은 sulci만 수식.
70189|include|negative|0|The third ventricle, both lateral ventricles, and sulci are of normal width.|양측 정상 폭. MRA와 gliosis는 별개.
69066|include|negative|0|Third ventricle and both lateral ventricles are of normal size.|양측 정상 크기. age-compatible은 sulci만 수식.
70113|include|negative|0|The third ventricle, both lateral ventricles, and sulci are of normal size.|양측 정상 크기.
70291|include|negative|0|The width of the third and lateral ventricles and hemispheric sulci is normal.|복수 정상 폭. facial nerve enhancement 추정은 별개.
68654|include|negative|0|The third ventricle and both lateral ventricles are of normal size.|양측 정상 크기 명시.
68298|include|negative|0|Third ventricle and lateral ventricles are of normal width.|복수 정상 폭. metastasis 평가 문맥과 별개.
69946|include|negative|0|The third ventricle, both lateral ventricles, and sulci are of normal width.|양측 정상 폭 명시.
69573|include|negative|0|The third ventricle, both lateral ventricles, and sulci are of normal size.|양측 정상 크기. pineal cyst와 별개.
68622|include|negative|0|Third ventricle and lateral ventricles are of normal size.|복수 정상 크기.
41333|include|negative|0|Third ventricle, both lateral ventricles, and sulci are of normal size.|양측 정상 크기.
36182|include|negative|0|The width of the third and lateral ventricles and hemispheric sulci is normal.|복수 정상 폭. multifocal mass 유지. 좌우 mass 위치의 report/impression 차이는 목표 크기에 영향을 주지 않음.
30484|include|negative|0|The width of the third and lateral ventricles and hemispheric sulci is normal.|복수 정상 폭. 후순위 검토만, cutoff 이후.
69276|include|negative|0|The width of the third and lateral ventricles and hemispheric sulci is normal.|복수 정상 폭. pineal enlargement는 별개. cutoff 이후.
70194|include|negative|0|Third ventricle, bilateral lateral ventricles, and sulci are of normal width.|양측 정상 폭. cutoff 이후 검토만.
69340|include|positive|0|Marked increase is observed in the lateral ventricle widths and 3rd ventricle width, and it is symmetric.|복수 측뇌실 대칭 폭 증가 명시. shunt·원인 불확실성은 크기 존재와 별개.
68412|include|positive|0|3rd and lateral ventricles; frontotemporal cerebral subarachnoid spaces are widened due to cerebral atrophy.|복수 측뇌실 위축 관련 확장 명시.
70917|unknown|unknown|0|The lateral ventricle and third ventricle are slightly prominent.|단수 대상. 양측 확대 해석 금지.
68807|include|positive|0|Lateral ventricles, third ventricle slightly prominent|복수 측뇌실 prominence. 경도 senile atrophy 유지.
70362|exclude|unilateral|0|compression of the right lateral ventricle, and resulting left monoventricular dilation persist.|우측 compression과 좌측만 확장. 양측 대상 불성립.
70842|include|positive|0|Lateral ventricles, third ventricle are mildly prominent.|복수 경도 prominence 명시.
67665|include|positive|0|an increase in the dilation previously observed in the lateral ventricle widths was noted|양측 현재 atrium 23/22mm와 증가된 확장 명시. 이전 검사와 비교하더라도 현재 크기 기술 존재.
70259|unknown|unknown|1|Asymmetric enlargement in the left lateral ventricle is a variant, and ventricles and sulci are normal.|좌측만 variant enlargement와 일반 정상 기술 동시. 양측 정답 미확인.
68616|include|positive|0|The 3rd and lateral ventricles are enlarged.|복수 확장 명시. white matter/thalami 정상과 고신호의 상충은 목표 크기와 별개.
68389|include|positive|0|Mild asymmetric prominence with left predominance is observed in the widths of the lateral ventricles|복수 폭 prominence에 좌측 predominance. 좌측만 확장이라고 쓰지 않았으며 전체 정상 주장 없음.
70433|include|positive|0|The third ventricle, both lateral ventricles, and sulci are enlarged secondary to central cerebral atrophy.|양측 위축 관련 확장 명시.
68783|unknown|unknown|0|Lateral ventricle, third ventricle are slightly prominent.|측뇌실 자체는 단수. bilateral temporal horns 확장은 부분영역 기술로 전체 양측 측뇌실 범위를 추정하지 않는다.
69253|include|positive|0|The 3rd and lateral ventricles are observed to be dilated|복수 측뇌실 확장. tectal lesion·ventriculostomy는 동반소견.
70042|unknown|unknown|0|The lateral ventricle and third ventricle are mildly prominent.|단수 대상. 양측 미확인.
68414|unknown|unknown|0|Lateral ventricle, third ventricle are widened.|좌측 atrium 확장과 단수 측뇌실 표현만. 양측을 추정하지 않는다.
70379|exclude|negative|0|third ventricle, both lateral ventricles and sulci are of normal width.|양측 정상 폭이며 후보 positive와 불일치. perivascular enlargements를 목표 확장으로 쓰지 않는다.
70005|unknown|unknown|0|Lateral ventricle and third ventricle are slightly prominent.|단수 대상. 양측 미확인.
68702|exclude|unilateral|0|Supratentorial ventricles and subarachnoid spaces are normal except for variant enlargement of the left lateral ventricle.|좌측만 variant 확장. 일반 정상의 예외로 분리되어 상충으로 보지 않음.
70116|include|positive|0|Compensated enlargement is present in the lateral ventricles|복수 측뇌실 확장과 impression dilation 일치. 우측 horn의 국소 compression은 전체 확장과 양립 가능하며 전반적 정상 크기 주장이 아님. artifact와 shunt 기록 유지.
70707|include|positive|0|Bilateral lateral ventricles, third ventricle are widened.|양측 확장 명시.
70654|include|positive|0|There is minimal widening compatible with atrophy in the third ventricle, both lateral ventricles|양측 최소 확장도 유지. 원인 설명과 존재를 구분.
70911|include|positive|0|The third and lateral ventricles are slightly prominent.|복수 경도 prominence 명시. chronic infarct 문맥 유지.
68627|exclude|not_positive|0|Third and lateral ventricles are normal, and the frontal subarachnoid space is widened.|목표 확장 없음. subarachnoid widening은 다른 구조. 일반 normal을 negative로 옮기지도 않는다.
70101|exclude|unknown|0|Central and peripheral CSF spaces widths are normal.|bilateral lateral ventricles는 gliosis 위치 문구만. 목표 확장 근거 없음. 원 제외 이유 미복원, 이번 원문 기반 새 판단.
69242|exclude|unilateral|0|There is asymmetric enlargement in the body of the right lateral ventricle secondary to thalamic volume loss|우측만 확장. 원 제외 이유 미복원, 이번 원문 기반 새 판단.
70410|unknown|unknown|0|The left lateral ventricle is variably wide, and there is mild enlargement in the frontal horns and frontal cerebral sulci.|좌측 variant와 frontal horns의 수식 범위 모호. 양측 전체를 추정하지 않음. 원 제외 이유 미복원, 이번 새 판단.
68528|unknown|unknown|0|Lateral ventricle and third ventricle are mildly prominent.|단수 대상. 양측 미확인.
70531|include|positive|0|Lateral ventricles, third ventricle are mildly prominent.|복수 경도 prominence 명시.
69184|include|positive|0|The lateral ventricles and third ventricle are slightly prominent.|복수 경도 prominence 명시.
68171|include|positive|0|Symmetric enlargements compatible with patient age are present in the lateral ventricles|복수 대칭 확장 명시. age-compatible 설명으로 음성 처리하지 않음. cutoff 이후 검토만.
70764|include|positive|0|The third ventricle, both lateral ventricles, and anterior interhemispheric fissure are enlarged secondary to frontal cerebral atrophy.|양측 위축 관련 확장 명시. impression 정상 문장은 frontal atrophy 예외를 유지. cutoff 이후 검토만.
68453|include|positive|0|The 3rd and lateral ventricles are enlarged.|복수 확장 명시. 비목표 midbrain 정상/atrophy 상충은 별도 기록. cutoff 이후 검토만.
70663|unknown|unknown|1|Central and peripheral CSF space widths are normal.|좌측 인접 측뇌실 ex-vacuo enlargement와 넓은 CSF 정상 폭 병기. 양측 미확인. cutoff 이후 검토만.
68239|exclude|unilateral|0|Partial dilation of the left lateral ventricle has developed due to decreased mass effect.|좌측만 부분 dilation. cutoff 이후 검토만.
'''


def main():
    ordered=read(OUT/'ordered_candidates.json')
    by={str(c['patient_uid']):c for rows in ordered.values() for c in rows}
    reports=read(OUT/'full_reports.json')
    old=read('results/iter_125/data/selection_lock.json')
    judgments={}
    for line in TABLE.strip().splitlines():
        pid,decision,polarity,conflict,quote,reason=line.split('|',5)
        assert pid not in judgments
        c=by[pid]
        r=reports[c['batch_id']][c['study_uid']]
        assert quote in r['report'], (pid,quote)
        quotes=[dict(section='report',quote=quote)]
        # 해당 사례에 필요한 반대/범위 제한 문구도 원문에 직접 연결한다.
        extra={15831:['Minimal asymmetric dilatation is observed in the right lateral ventricle.'],
               68783:['Bilateral temporal horns are enlarged.'],
               70116:['The right trigone, occipital horn and posterior segment of the corpus callosum are compressed due to hematoma and edema.'],
               70663:['Ex-vacuo enlargement accompanies the adjacent lateral ventricle.']}
        for q in extra.get(int(pid),[]):
            assert q in r['report']
            quotes.append(dict(section='report',quote=q))
        judgments[pid]=dict(decision=decision,polarity=polarity,target='양측/명시적 복수 측뇌실' if decision=='include' else '원 인용의 대상 범위에 한정',
                           conflict=bool(int(conflict)),reason_ko=reason,quotes=quotes,
                           full_fields_reviewed=['report','findings','impression'],
                           review_origin='이번 원문 직접 검토의 새 판단; 과거 판단의 자동 승계 아님',
                           original_exclusion_reason=old['excluded_after_review'].get(pid),
                           original_reason_missing=int(pid) in [70101,69242,70410],
                           source_snapshot_sha256=sha(OUT/'full_reports.json'),
                           reviewed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    save(OUT/'judgments.json',judgments)
    print('reviewed',len(judgments))


if __name__=='__main__': main()
