using Microsoft.VisualBasic;
using System;
using System.Diagnostics;
using static System.Windows.Forms.VisualStyles.VisualStyleElement.TaskbarClock;

namespace DLAPrevention
{
    /// <summary>
    /// Class with DLA_Prevention's array of patient assessments
    /// </summary>
    public partial class evaluacionesDLAPrevention
    {
        /// <summary>
        /// Date and time when the patient assessments export was generated

        /// </summary>
        public string creationdatetime { get; set; }
        /// <summary>
        /// Object containing an array of assessments
        /// </summary>
        public evaluacion[] evaluaciones { get; set; }

    }
    /// <summary>
    /// Assessment of a patient
    /// </summary>
    public partial class evaluacion
    {
        /// <summary>
        /// Demographics object
        /// </summary>
        public class_demographics demographics { get; set; }
        /// <summary>
        /// clinical object
        /// </summary>
        public class_clinical clinical { get; set; }
        /// <summary>
        /// caide_risk_factors object
        /// </summary>
        public class_caide_risk_factors caide_risk_factors { get; set; }
        /// <summary>
        /// health_data object
        /// </summary>
        public class_health_data health_data { get; set; }
        /// <summary>
        /// scales object
        /// </summary>
        public class_scales scales { get; set; }
        /// <summary>
        /// scales_pilot_specific object
        /// </summary>
        public class_scales_pilot_specific scales_pilot_specific { get; set; }
        /// <summary>
        /// eq5d5l_questionaire object
        /// </summary>
        public class_eq5d5l_questionaire eq5d5l_questionaire { get; set; }
        /// <summary>
        /// opqolbrief object
        /// </summary>
        public class_opqolbrief opqolbrief { get; set; }
        /// <summary>
        /// cri_questionnaire object
        /// </summary>
        public class_cri_questionnaire cri_questionnaire { get; set; }
        /// <summary>
        /// bdi2_questionnaire object
        /// </summary>
        public class_bdi2_questionnaire bdi2_questionnaire { get; set; }
        /// <summary>
        /// ipaq_questionnaire object
        /// </summary>
        public class_ipaq_questionnaire ipaq_questionnaire { get; set; }
        /// <summary>
        /// covid_questionnaire object
        /// </summary>
        public class_covid_questionnaire covid_questionnaire { get; set; }
        /// <summary>
        /// utec_questionnaire object
        /// </summary>
        public class_utec_questionnaire utec_questionnaire { get; set; }
        /// <summary>
        /// sus_questionnaire object
        /// </summary>
        public class_sus_questionnaire sus_questionnaire { get; set; }
        /// <summary>
        /// cog_pred_screening object
        /// </summary>
        public class_cog_pred_screening cog_pred_screening { get; set; }

    }

    /// <summary>
    /// Demographic Data class
    /// </summary>
    public partial class class_demographics
    {
        /// <summary>
        /// UUIDCOMFORTAGE will be the patient's identifier, concatenated as follows:
        /// "Pilot.11.2.GradiorDLAPrev." + ID_Identia
        /// The ID_Identia is stored in the database in the Patients table, field sCIP
        /// Example: Pilot.11.2.GradiorDLAPrev.ID_M_Rango3_056_ED2
        /// </summary>
        public string study_id { get; set; }
        /// <summary>
        /// Assessment date
        /// </summary>
        public string date_enrolled { get; set; }
        /// <summary>
        /// Patient's age at the assessment date
        /// </summary>
        public string age { get; set; }
        /// <summary>
        /// Years of education
        /// </summary>
        public string edu_years { get; set; }
        /// <summary>
        /// Patient's gender
        /// Value: 0=Female; 1= male
        /// </summary>
        public string gender { get; set; }
        /// <summary>
        /// Current employment status  
        /// Values: 0 = Employed, 1 = Unemployed, 2 = Retired, 3 = Never worked, 4 = Unknown / Not Reported
        /// </summary>
        public string working_status { get; set; }
        /// <summary>
        /// Civil Status at the assessment date  
        /// Value: 0, Single; 1, Married; 2, Divorced; 3, Widow
        /// </summary>
        public string civil_status { get; set; }
        /// <summary>
        /// Living Status
        /// Values: 0 = Alone, 1 = With partner, 2 = With children, 3 = With partner and children, 4 = With someone else, 5 = In Hospice/Hospitalized
        /// </summary>
        public string living_status { get; set; }
        /// <summary>
        /// Complete class if all fields are filled  
        /// Values: 0 = Incomplete, 1 = Not verified, 2 = Complete
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// Clinical class
    /// </summary>
    public partial class class_clinical
    {
        /// <summary>
        /// Relative with dementia: 0 = NO, 1 = YES  
        /// </summary>
        public string relatives_with_dementia { get; set; }
        /// <summary>
        /// Que Familiares con demencia 1=mother, 2=father, 3=brother(s), 4=sister(s)
        /// specify_which_relatives = {1,2}
        /// </summary>
        public string[] specify_which_relatives { get; set; }
        /// <summary>
        /// Main class for managing the Cumulative Illness Rating Scale for Geriatrics (CIRS-G).
        /// Values: 0 = No problem, 1 = Mild problem, 2 = Moderate problem, 3 = Severe problem, 4 = Extremely severe or disabling problem
        /// CIRS-G: cardiac
        /// </summary>
        public string cardiac { get; set; }
        /// <summary>
        /// CIRS-G: vascular
        /// </summary>
        public string vascular { get; set; }
        /// <summary>
        /// CIRS-G: hematological
        /// </summary>
        public string hematological { get; set; }
        /// <summary>
        /// CIRS-G: respiratory
        /// </summary>
        public string respiratory { get; set; }
        /// <summary>
        /// CIRS-G: ophthalmological_and_orl
        /// </summary>
        public string ophthalmological_and_orl { get; set; }
        /// <summary>
        /// CIRS-G: upper_gastrointestinal
        /// </summary>
        public string upper_gastrointestinal { get; set; }
        /// <summary>
        /// CIRS-G: lower_gastrointestinal
        /// </summary>
        public string lower_gastrointestinal { get; set; }
        /// <summary>
        /// CIRS-G: hepatic_and_pancreatic
        /// </summary>
        public string hepatic_and_pancreatic { get; set; }
        /// <summary>
        /// CIRS-G: renal
        /// </summary>
        public string renal { get; set; }
        /// <summary>
        /// CIRS-G: genitourinary
        /// </summary>
        public string genitourinary { get; set; }
        /// <summary>
        /// CIRS-G: musculoskeletal_and_tegume
        /// </summary>
        public string musculoskeletal_and_tegume { get; set; }
        /// <summary>
        /// CIRS-G: neurological
        /// </summary>
        public string neurological { get; set; }
        /// <summary>
        /// CIRS-G: endocrine_metabolic_breast
        /// </summary>
        public string endocrine_metabolic_breast { get; set; }
        /// <summary>
        /// CIRS-G: psychiatric
        /// </summary>
        public string psychiatric { get; set; }
        /// <summary>
        /// CIRS-G: total_score = sum of all item values, ranging from 0 (no illness burden) to a maximum of 56 (severe burden across all systems).
        /// </summary>
        public string total_score { get; set; }
        /// <summary>
        /// Complete class if all fields are filled  
        /// Values: 0 = Incomplete, 1 = Not verified, 2 = Complete
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// caide_risk_factors class
    /// </summary>
    public partial class class_caide_risk_factors
    {
        /// <summary>
        /// Hypertension values; SBP ≤140 mmHg = 1 - Not hypertensive; SBP >140 mmHg = 2 - Hypertensive  
        /// </summary>
        public string hypertension { get; set; }
        /// <summary>
        /// Takes medication for hypertension; 1 = YES / 0 = NO
        /// </summary>
        public string hypertension_med { get; set; }
        /// <summary>
        /// Cholesterol values; If ≤6.5 mmol/L = 1 - No high cholesterol, If >6.5 mmol/L = 2 - Has high cholesterol  
        /// </summary>
        public string cholesterol { get; set; }
        /// <summary>
        /// Takes medication for cholesterol; 1 = YES / 0 = NO
        /// </summary>
        public string cholesterol_med { get; set; }
        /// <summary>
        /// Performs physical activity: Active = 1 / Inactive = 2  
        /// </summary>
        public string physical_activity { get; set; }
        /// <summary>
        /// Complete class if all fields are filled  
        /// Values: 0 = Incomplete, 1 = Not verified, 2 = Complete
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// health_data class
    /// </summary>
    public partial class class_health_data
    {
        /// <summary>
        /// Height (m)
        /// </summary>
        public string height { get; set; }
        /// <summary>
        /// Weight (kg)
        /// </summary>
        public string weight { get; set; }
        /// <summary>
        /// Body Mass Index
        /// Calculate (BMI = weight (kg) / [height (m)]²)
        /// </summary>
        public string bmi { get; set; }
        /// <summary>
        /// Systolic blood pressure (mmHg – e.g., 120)
        /// </summary>
        public string bp_sys { get; set; }
        /// <summary>
        /// Diastolic blood pressure (mmHg – e.g., 80)
        /// </summary>
        public string bp_dia { get; set; }
        /// <summary>
        /// Heart rate (beats per minute (bpm)
        /// </summary>
        public string heart_rate { get; set; }
        /// <summary>
        /// Smoking status: smoker, non-smoker, or Previously
        /// Value: 1 = Yes (current smoker), 2 = No, 3 = Previously
        /// </summary>
        public string smoke_status { get; set; }
        /// <summary>
        /// Number of years smoking (if previously smoked)
        /// If the answer to smoke_status is 3, fill in the value
        /// </summary>
        public string smoke_years { get; set; }
        /// <summary>
        /// Alcohol consumption measure: 1 = AUDIT Score, 2 = Units per Week
        /// </summary>
        public string alcohol_measure { get; set; }
        /// <summary>
        /// AUDIT scale score
        /// </summary>
        public string audit_score { get; set; }
        /// <summary>
        /// List of medication
        /// Concatenate the list into a string
        /// </summary>
        public string current_med_therapy { get; set; }
        /// <summary>
        /// Class Complete - Form complete=If the fields Height, weight and imc are filled in.
        /// Values: 0=Incomplete, 1=Not checked, 2=Complete
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// scales class
    /// </summary>
    public partial class class_scales
    {
        /// <summary>
        /// MMSE (Mini-Mental State Examination) result – Raw score – 0 to 30
        /// </summary>
        public string ment_status { get; set; }
        /// <summary>
        /// CDR-SB (Clinical Dementia Rating – Sum of Boxes) result – Raw score 0 to 18
        /// </summary>
        public string cdr_sb { get; set; }
        /// <summary>
        /// ADL result (Katz Index – Basic Activities of Daily Living) – Raw score 0 to 6
        /// </summary>
        public string adl { get; set; }
        /// <summary>
        /// Instrumental Activities of Daily Living result (Lawton & Brody) – Raw score 0 to 8
        /// </summary>
        public string iadl { get; set; }
        /// <summary>
        /// Option button 5,6,7,8 (Maximum IADL Applicable)
        /// </summary>
        public string max_iadl { get; set; }
        /// <summary>
        /// Complete class if all fields are filled  
        /// Values: 0 = Incomplete, 1 = Not verified, 2 = Complete
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// scales_pilot_specific class
    /// </summary>
    public partial class class_scales_pilot_specific
    {
        /// <summary>
        /// Geriatric Depression Scale (GDS) YESAVAGE > 65 – Raw score 0 to 30
        /// </summary>
        public string ger_depres { get; set; }
        /// <summary>
        /// Complete class if all fields are filled  
        /// Values: 0 = Incomplete, 1 = Not verified, 2 = Complete
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// eq5d5l_questionaire class
    /// </summary>
    public partial class class_eq5d5l_questionaire
    {
        /// <summary>
        /// mobility: Value between 1 and 5
        /// </summary>
        public string eq5d_mobility { get; set; }
        /// <summary>
        /// self-care : Value between 1 and 5
        /// </summary>
        public string eq5d_selfcare { get; set; }
        /// <summary>
        /// Usual Activities: Value between 1 and 5
        /// </summary>
        public string eq5d_usual { get; set; }
        /// <summary>
        /// Pain/Discomfort: Value between 1 and 5
        /// </summary>
        public string eq5d_pain { get; set; }
        /// <summary>
        /// Anxiety/Depression: Value between 1 and 5
        /// </summary>
        public string eq5d_anxiety { get; set; }
        /// <summary>
        /// Concatenated response vector
        /// </summary>
        public string eq5d_score { get; set; }
        /// <summary>
        /// Complete class if all fields are filled  
        /// Values: 0 = Incomplete, 1 = Not verified, 2 = Complete
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// opqolbrief class
    /// Each of the 13 items is scored Strongly agree=1, Agree=2, Neither=3, Disagree=4, Strongly disagree=5.
    /// The items are summed for a total OPQOL-Brief score, then positive items are reverse coded, so that higher scores represented higher QoL.
    /// </summary>
    public partial class class_opqolbrief
    {
        /// <summary>
        /// Q1. enjoy my life overall
        /// </summary>
        public string q1_enjoy_my_life_overall { get; set; }
        /// <summary>
        /// Q2. look forward to things
        /// </summary>
        public string q2_look_forward_to_things { get; set; }
        /// <summary>
        /// Q3. am healthy enough to get out and about
        /// </summary>
        public string q3_healthy_enough_to_get { get; set; }
        /// <summary>
        /// Q4. My family, friends or neighbours would help me if needed
        /// </summary>
        public string q4_family_friends_or_neigh { get; set; }
        /// <summary>
        /// Q5. have social or leisure activities/hobbies that I enjoy doing
        /// </summary>
        public string q5_social_or_leisure_a { get; set; }
        /// <summary>
        /// Q6. try to stay involved with things
        /// </summary>
        public string q6_try_to_stay_involved { get; set; }
        /// <summary>
        /// Q7. am healthy enough to have my independence
        /// </summary>
        public string q7_healthy_enough_to_hav { get; set; }
        /// <summary>
        /// Q8. can please myself what I do
        /// </summary>
        public string q8_please_myself_what_i { get; set; }
        /// <summary>
        /// Q9. feel safe where I live
        /// </summary>
        public string q9_feel_safe_where_i_live { get; set; }
        /// <summary>
        /// Q10. get pleasure from my home
        /// </summary>
        public string q10_pleasure_from_my_hom { get; set; }
        /// <summary>
        /// Q11. take life as it comes and make the best of things
        /// </summary>
        public string q11_take_life_as_it_comes { get; set; }
        /// <summary>
        /// Q12. feel lucky compared to most people
        /// </summary>
        public string q12_i_feel_lucky { get; set; }
        /// <summary>
        /// Q13. have enough money to pay for household bills
        /// </summary>
        public string q13_enough_money_to_pay { get; set; }
        /// <summary>
        /// Sum of values from Q1 to Q13
        /// </summary>
        public string opqol_total_score { get; set; }
        /// <summary>
        /// Complete class if all fields are filled  
        /// Values: 0 = Incomplete, 1 = Not verified, 2 = Complete
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// cri_questionnaire class
    /// </summary>
    public partial class class_cri_questionnaire
    {
        /// <summary>
        /// Cri education index
        /// </summary>
        public string cri_edu_ind { get; set; }
        /// <summary>
        /// Cri work index
        /// </summary>
        public string cri_work_ind { get; set; }
        /// <summary>
        /// Cri leisure time index
        /// </summary>
        public string cri_leisure_ind { get; set; }
        /// <summary>
        /// Cri Total index
        /// </summary>
        public string cri_total_score { get; set; }
        /// <summary>
        /// Complete class if all fields are filled  
        /// Values: 0 = Incomplete, 1 = Not verified, 2 = Complete
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// bdi2_questionnaire class
    /// Beck Depression Inventory-II (BDI-II) classification:
    /// 0–13: Minimal or mild depression
    /// 14–19: Mild to moderate depression
    /// 20–28: Moderate to severe depression
    /// 29–63: Severe depression
    /// </summary>
    public partial class class_bdi2_questionnaire
    {
        /// <summary>
        /// Raw score between 0 and 63 (integer)
        /// </summary>
        public string bdi2_total_score { get; set; }
        /// <summary>
        /// Complete class if all fields are filled  
        /// Values: 0 = Incomplete, 1 = Not verified, 2 = Complete
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// Clase ipaq_questionnaire
    /// International Physical Activity Questionnaire (IPAQ) classification:
    /// - Low: < 600 MET-minutes/week
    /// - Moderate: 600 to 1500 MET-minutes/week
    /// - High: ≥ 1500 MET-minutes/week
    /// </summary>
    public partial class class_ipaq_questionnaire
    {
        /// <summary>
        /// High physical activity level
        /// </summary>
        public string ipap_vigorous_physical_activity { get; set; }
        /// <summary>
        /// Moderate physical activity level 
        /// </summary>
        public string ipap_moderate_physical_activity { get; set; }
        /// <summary>
        /// Physical activity level – Walking 
        /// </summary>
        public string ipap_physical_activity_walking { get; set; }
        /// <summary>
        /// Total score – Sum of all recorded values
        /// </summary>
        public string ipap_total_score { get; set; }
        /// <summary>
        /// Complete class if all fields are filled  
        /// Values: 0 = Incomplete, 1 = Not verified, 2 = Complete
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// covid_questionnaire class
    /// </summary>
    public partial class class_covid_questionnaire
    {
        /// <summary>
        /// If you have passed the Covid 0=NO, 1=YES
        /// </summary>
        public string covid_had_covid { get; set; }
        /// <summary>
        /// Number of times the Covid has passed
        /// </summary>
        public string covid_times_infected { get; set; }
        /// <summary>
        /// Symptom Difficulty in breathing 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_breathing { get; set; }
        /// <summary>
        /// Symptom Muscle Pain 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_muscle_pain { get; set; }
        /// <summary>
        /// Symptom chills 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_chills { get; set; }
        /// <summary>
        /// Symptom Sore Throat 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_sore_throat { get; set; }
        /// <summary>
        /// Symptom Fever 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_fever { get; set; }
        /// <summary>
        /// Headache Symptom 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_headache { get; set; }
        /// <summary>
        /// Symptom Diarrhoea 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_diarrhea { get; set; }
        /// <summary>
        /// Symptom Rash 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_rash { get; set; }
        /// <summary>
        /// Symptom Loss of Smell 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_loss_smell { get; set; }
        /// <summary>
        /// Symptom Loss of Taste 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_loss_taste { get; set; }
        /// <summary>
        /// Symptom Fatigue 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_fatigue { get; set; }
        /// <summary>
        /// Symptom Other symptoms 0=NO, 1=YES
        /// </summary>
        public string covid_symptom_other { get; set; }
        /// <summary>
        /// Symptom Other descriptive text
        /// </summary>
        public string covid_symptom_other_description { get; set; }
        /// <summary>
        /// If you are vaccinated for COVID 0=NO, 1=YES
        /// </summary>
        public string covid_vaccinated { get; set; }
        /// <summary>
        /// Number of COVID vaccine doses
        /// </summary>
        public string covid_num_doses { get; set; }
        /// <summary>
        /// If you felt isolated during confinement
        /// 1- Not isolated at all, 2-Little isolated, 3-Moderately isolated, 4-Very isolated, 5-Extremely isolated
        /// </summary>
        public string covid_feeling_isolated { get; set; }
        /// <summary>
        /// Clase Completa si todos los campos rellenos 
        /// Valores: 0=Incompleto, 1=No verificado, 2=Completo
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// Questionnaire for the use of technology class
    /// Values: 1=Never, 2=Almost Never, 3=Sometimes, 4=Almost Always, 5=Always
    /// </summary>
    public partial class class_utec_questionnaire
    {
        /// <summary>
        /// Frequency of computer/tablet use
        /// </summary>
        public string utec_freq_computer_use { get; set; }
        /// <summary>
        /// Frequency of mobile phone use
        /// Values: 1=Never, 2=Almost Never, 3=Sometimes, 4=Almost Always, 5=Always
        /// </summary>
        public string utec_freq_mobile_use { get; set; }
        /// <summary>
        /// Frequency of television use
        /// Values: 1=Never, 2=Almost Never, 3=Sometimes, 4=Almost Always, 5=Always
        /// </summary>
        public string utec_freq_tv_use { get; set; }
        /// <summary>
        /// Frequency of email use
        /// Values: 1=Never, 2=Almost Never, 3=Sometimes, 4=Almost Always, 5=Always
        /// </summary>
        public string utec_freq_email_use { get; set; }
        /// <summary>
        /// Frequency of social media use
        /// Values: 1=Never, 2=Almost Never, 3=Sometimes, 4=Almost Always, 5=Always
        /// </summary>
        public string utec_freq_social_media_use { get; set; }
        /// <summary>
        /// Clase Completa si todos los campos rellenos 
        /// Valores: 0=Incompleto, 1=No verificado, 2=Completo
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// System Usability Scale (SUS) class
    /// </summary>
    public partial class class_sus_questionnaire
    {
        /// <summary>
        /// Total is calculated as follows:
        /// P1 = Sum of odd-numbered items - 5;
        /// P2 = 25 - Sum of even-numbered items;
        /// Total = (P1 + P2) * 2.5
        /// </summary>
        public string sus_total_score { get; set; }
        /// <summary>
        /// Clase Completa si todos los campos rellenos 
        /// Valores: 0=Incompleto, 1=No verificado, 2=Completo
        /// </summary>
        public string complete { get; set; }
    }

    /// <summary>
    /// Core class for predictive cognitive screening.
    /// It manages a neuropsychological assessment using tests like Corsi, Rey-Osterrieth, Stroop, and TAVEC.
    /// Z-scores (43 items) and years of education are used to classify users into cognitive types and subtypes:
    /// - Types: NORMAL, VERY MILD COGNITIVE DECLINE, MILD COGNITIVE DECLINE
    /// - Subtypes: based on amnestic and visuoconstruction/processing speed profiles.
    /// This classification supports AI-driven predictive analysis.
    /// </summary>
    public partial class class_cog_pred_screening
    {
        /// <summary>
        /// Corsi Block Tapping Test  Forward z-score
        /// </summary>
        public string cog_pred_corsi_forward_zscore { get; set; }
        /// <summary>
        /// Corsi Block Tapping Test  Forward z-score
        /// </summary>
        public string cog_pred_corsi_backward_zscore { get; set; }
        /// <summary>
        /// Corsi Block Tapping Test Total z-score
        /// </summary>
        public string cog_pred_corsi_total_zscore { get; set; }
        /// <summary>
        /// Rey Osterrieth Complex Figure Test Copy z-score
        /// </summary>
        public string cog_pred_rcf_copy_zscore { get; set; }
        /// <summary>
        /// Rey Osterrieth Complex Figure Test Immediate Recall z-score
        /// </summary>
        public string cog_pred_rcf_recall_zscore { get; set; }
        /// <summary>
        /// Rey Osterrieth Complex Figure Test Time to Copy z-score
        /// </summary>
        public string cog_pred_rcf_timecopy_zscore { get; set; }
        /// <summary>
        /// Stroop Test – Word Reading z-score
        /// </summary>
        public string cog_pred_stroop_word_zscore { get; set; }
        /// <summary>
        /// Stroop Test – Color Naming z-score
        /// </summary>
        public string cog_pred_stroop_color_zscore { get; set; }
        /// <summary>
        /// Stroop Test – Color–Word  z-score
        /// </summary>
        public string cog_pred_stroop_colword_zscore { get; set; }
        /// <summary>
        /// Stroop Test – Interference z-score (PT)
        /// </summary>
        public string cog_pred_stroop_interf_zscore { get; set; }
        /// <summary>
        /// Tavec - 1: Immediate Recall – List A, Trial 1
        /// </summary>
        public string cog_pred_tavec_imrec_a1 { get; set; }
        /// <summary>
        /// Tavec - 2: Immediate Recall – List A, Trial 5-A5
        /// </summary>
        public string cog_pred_tavec_imrec_a5 { get; set; }
        /// <summary>
        /// Tavec - 3: Immediate Recall – List A, Total Trials
        /// </summary>
        public string cog_pred_tavec_imrec_atotal { get; set; }
        /// <summary>
        /// Tavec - 4: Immediate Recall – List B
        /// </summary>
        public string cog_pred_tavec_imrec_b { get; set; }
        /// <summary>
        /// Tavec - 5: Percentage of words from the primacy region
        /// </summary>
        public string cog_pred_tavec_primacy_pct { get; set; }
        /// <summary>
        /// Tavec - 6: Percentage of words from the middle region
        /// </summary>
        public string cog_pred_tavec_middle_pct { get; set; }
        /// <summary>
        /// Tavec - 7: Percentage of words originating from the recency region
        /// </summary>
        public string cog_pred_tavec_recency_pct { get; set; }
        /// <summary>
        /// Tavec - 8: Short Delay Free Recall
        /// </summary>
        public string cog_pred_tavec_shortdel_free { get; set; }
        /// <summary>
        /// Tavec - 9: Short Delay Cued Recall
        /// </summary>
        public string cog_pred_tavec_shortdel_cued { get; set; }
        /// <summary>
        /// Tavec - 10: Long-Delay Free Recall
        /// </summary>
        public string cog_pred_tavec_longdel_free { get; set; }
        /// <summary>
        /// Tavec - 11: Long-Delay Cued Recall
        /// </summary>
        public string cog_pred_tavec_longdel_cued { get; set; }
        /// <summary>
        /// Tavec - 12: Use of semantic strategy in immediate recall of List A
        /// </summary>
        public string cog_pred_tavec_imrec_sem_a { get; set; }
        /// <summary>
        /// Tavec - 13: Use of semantic strategy in immediate recall of List B
        /// </summary>
        public string cog_pred_tavec_imrec_sem_b { get; set; }
        /// <summary>
        /// Tavec - 14: Use of semantic strategy in short-delay free recall
        /// </summary>
        public string cog_pred_tavec_shortdel_free_sem { get; set; }
        /// <summary>
        /// Tavec - 15: Use of semantic strategy in long-delay free recall
        /// </summary>
        public string cog_pred_tavec_longdel_free_sem { get; set; }
        /// <summary>
        /// Tavec - 16: Use of serial strategy in immediate recall of List A
        /// </summary>
        public string cog_pred_tavec_imrec_serial_a { get; set; }
        /// <summary>
        /// Tavec - 17: Use of serial strategy in immediate recall of List B
        /// </summary>
        public string cog_pred_tavec_imrec_serial_b { get; set; }
        /// <summary>
        ///  Tavec - 18: Use of serial strategy in short-delay free recall
        /// </summary>
        public string cog_pred_tavec_shortdel_free_ser { get; set; }
        /// <summary>
        /// Tavec - 19: Use of serial strategy in long-delay free recall
        /// </summary>
        public string cog_pred_tavec_longdel_free_ser { get; set; }
        /// <summary>
        /// Tavec - 20: Total number of perseverations
        /// </summary>
        public string cog_pred_tavec_total_perseverations { get; set; }
        /// <summary>
        /// Tavec - 21: Intrusions –Free Recall
        /// </summary>
        public string cog_pred_tavec_intrusions_free { get; set; }
        /// <summary>
        /// Tavec - 22: Intrusions –Cued Recall
        /// </summary>
        public string cog_pred_tavec_intrusions_cued { get; set; }
        /// <summary>
        /// Tavec - 23: Number of correct responses in recognition task
        /// </summary>
        public string cog_pred_tavec_recognition_hits { get; set; }
        /// <summary>
        /// Tavec - 24: Number of false positives in recognition task
        /// </summary>
        public string cog_pred_tavec_recognition_fp { get; set; }
        /// <summary>
        /// Tavec - 25: Discriminability index
        /// </summary>
        public string cog_pred_tavec_index1_discriminability { get; set; }
        /// <summary>
        /// Tavec - 26: Response Bias index
        /// </summary>
        public string cog_pred_tavec_index2_bias { get; set; }
        /// <summary>
        /// Tavec - 27: Immediate Recall List B vs List A
        /// </summary>
        public string cog_pred_tavec_index3 { get; set; }
        /// <summary>
        /// Tavec - 28: Short Delay Free Recall vs Immediate Recall A5
        /// </summary>
        public string cog_pred_tavec_index4 { get; set; }
        /// <summary>
        /// Tavec - 29: Short Delay Cued Recall vs Long-Delay Cued Recall
        /// </summary>
        public string cog_pred_tavec_index5 { get; set; }
        /// <summary>
        /// Tavec - 30: Long-Delay Free Recall vs Short-Delay Free Recall
        /// </summary>
        public string cog_pred_tavec_index6 { get; set; }
        /// <summary>
        /// Tavec - 31: Long-Delay Cued Recall  vs Long-Delay Free Recall
        /// </summary>
        public string cog_pred_tavec_index7 { get; set; }
        /// <summary>
        /// Tavec - 32: Recognition vs Long-Delay Free Recall
        /// </summary>
        public string cog_pred_tavec_index8 { get; set; }
        /// <summary>
        /// Tavec - 33: Recognition vs Long-Delay Cued Recall 
        /// </summary>
        public string cog_pred_tavec_index9 { get; set; }


        /// <summary>
        /// Preliminary cognitive screening
        /// </summary>
        public string cog_pred_clinical_evaluation_type { get; set; }
        /// <summary>
        /// Predictive assessment for AI-based analysis
        /// </summary>
        public string cog_pred_clinical_evaluation_subtype { get; set; }
        /// <summary>
        /// Clase Completa si todos los campos rellenos 
        /// Valores: 0=Incompleto, 1=No verificado, 2=Completo
        /// </summary>
        public string complete { get; set; }
    }


}