
import json
import pandas as pd
from typing import Dict, List, Any
# from shared import logger

# logger = logger.get_logger()



def parse_time_str(time_str: str) -> tuple[int, int]:
    start, end = map(int, time_str.split('-'))
    return start, end
def is_time_fully_covered(staff_time: str, patient_time: str) -> bool:
    try:
        staff_start, staff_end = parse_time_str(staff_time)
        patient_start, patient_end = parse_time_str(patient_time)
        return staff_start <= patient_start and staff_end >= patient_end
    except:
        return False
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        # logger.info("Received event:", event)
        if isinstance(event.get('body'), str):
            event = json.loads(event['body'])

        print("Received event:")
        print(json.dumps(event, indent=2))


        patient_request = event.get('patient_request', {})
        staff_preferences_list = event.get('staff_preferences', [])
        if not patient_request or not staff_preferences_list:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing patient_request or staff_preferences'})
            }
        staff_df = pd.DataFrame(staff_preferences_list)
        matching_results = []
        for index, staff in staff_df.iterrows():
            import ast
            for field in ['preferred_regions', 'meal_types_supported', 'certifications']:
                if isinstance(staff.get(field), str):
                    try:
                        staff[field] = ast.literal_eval(staff[field])
                    except:
                        staff[field] = [staff[field]]
            if 'role' in patient_request and patient_request['role'] != staff.get('role'):
                continue
            if 'language' in patient_request and patient_request['language'] != staff.get('language'):
                continue
            patient_region = patient_request.get('required_regions', [])[0]
            staff_regions = staff.get('preferred_regions', [])
            if isinstance(staff_regions, str):
                try:
                    staff_regions = ast.literal_eval(staff_regions)
                except:
                    staff_regions = [staff_regions]
            if patient_region not in staff_regions:
                continue
            all_patient_days_covered = True
            total_overlap_hours = 0.0
            weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            patient_days = patient_request.get("preferred_days", {})
            for day in weekdays:
                patient_time = patient_days.get(day, None)
                staff_time_value = staff.get(day, 'off')  # ✅ 반드시 추가해야 함
                status_value = staff.get(f'Status{day}', 'off')

                if patient_time is not None:
                    if status_value == 'Available':
                        # 'Available' 상태일 때 staff_time_value가 시간 문자열이면 비교
                        if isinstance(staff_time_value, str) and '-' in staff_time_value:
                            if is_time_fully_covered(staff_time_value, patient_time):
                                p_start, p_end = parse_time_str(patient_time)
                                total_overlap_hours += float(p_end - p_start)
                            else:
                                all_patient_days_covered = False
                                break
                        else:
                            # 시간 정보가 없으면 기본값 적용
                            p_start, p_end = parse_time_str(patient_time)
                            total_overlap_hours += float(p_end - p_start)
                    else:
                        all_patient_days_covered = False
                        break

            if not all_patient_days_covered or total_overlap_hours == 0:
                continue
            if patient_request.get('license_status') == 'Active' and staff.get('license_status') != 'Active':
                continue
            if patient_request.get('eligibility_status') == 'Eligible' and staff.get('eligibility_status') != 'Eligible':
                continue
            score = 0
            patient_gender = patient_request.get('preferred_client_gender')
            staff_gender = staff.get('preferred_client_gender')
            if patient_gender and staff_gender:
                if staff_gender == 'No preference':
                    score += 10
                elif patient_gender == staff_gender:
                    score += 20
            if patient_request.get('pet_friendly') == staff.get('pet_friendly'):
                score += 5
            if patient_request.get('can_cook_meal') == staff.get('can_cook_meal'):
                score += 5
            if patient_request.get('parking_required') == staff.get('parking_required'):
                score += 5
            if patient_request.get('smoking_tolerance') == staff.get('smoking_tolerance'):
                score += 5
            patient_meal_types = set(patient_request.get('required_meal_types', []))
            staff_meal_types = set(staff.get('meal_types_supported', []))
            if patient_meal_types and staff_meal_types:
                if patient_meal_types.issubset(staff_meal_types):
                    score += 10
                elif patient_meal_types.intersection(staff_meal_types):
                    score += 5
            patient_certs = set(patient_request.get('required_certifications', []))
            staff_certs = set(staff.get('certifications', []))
            if patient_certs and staff_certs and patient_certs.issubset(staff_certs):
                score += 15
            score += int(total_overlap_hours * 2)
            matching_results.append({
                'NPI': staff.get('NPI'),
                'name': staff.get('Name'),
                'score': score,
                'overlap_hours': total_overlap_hours,
                **{k: staff[k] for k in staff.keys() if k not in ['NPI', 'Name']}
            })
        matching_results_sorted = sorted(matching_results, key=lambda x: x['score'], reverse=True)[:10]
        return {
            'statusCode': 200,
            'body': json.dumps(matching_results_sorted, ensure_ascii=False)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


