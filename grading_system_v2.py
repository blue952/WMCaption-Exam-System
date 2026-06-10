#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
World Model Caption 自动评分系统 - 带进度条版本
支持客观题自动评分 + Ollama主观题语义评分
适配问卷星Excel格式
"""

import json
import os
import re
import csv
import requests
import sys
from typing import List, Dict, Any, Tuple
from difflib import SequenceMatcher
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def print_progress_bar(iteration, total, prefix='', suffix='', length=50, fill='█'):
    """打印进度条"""
    percent = f"{100 * (iteration / float(total)):.1f}"
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end='', flush=True)
    if iteration == total:
        print()


class GradingSystem:
    """评分系统"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434", total_score: float = 100):
        self.ollama_url = ollama_url
        self.model = "qwen3:8b"
        self.question_map = {}
        self.objective_types = ['单选', '判断', '多选', '填空']
        self.subjective_types = ['简答', '情景', '综合']
        self.total_score = total_score  # 考试总分
        self.score_per_question = 1.0   # 每题分值，后面根据题目数量计算
    
    def load_exam_data(self, exam_json_path: str) -> Dict:
        """加载考试数据"""
        with open(exam_json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def load_question_map(self, map_path: str) -> Dict:
        """加载题号映射文件"""
        with open(map_path, 'r', encoding='utf-8') as f:
            self.question_map = json.load(f)
            print(f"✓ 加载题号映射，共 {len(self.question_map)} 题")
            return self.question_map
    
    def build_question_map_from_exam(self, exam_data: Dict) -> Dict:
        """从试卷数据构建题号映射"""
        self.question_map = {}
        for idx, q in enumerate(exam_data['questions'], 1):
            self.question_map[q['q']] = idx
        return self.question_map
    
    def load_answers_from_wjx_excel(self, excel_path: str) -> List[Dict]:
        """从问卷星导出的Excel加载学生答案"""
        try:
            import pandas as pd
        except ImportError:
            print("✗ 错误: 需要安装 pandas 来读取Excel文件")
            print("  请运行: pip install pandas openpyxl")
            return []
        
        df = pd.read_excel(excel_path)
        
        meta_columns = ['序号', '用户ID', '提交答卷时间', '所用时间', 
                       '来源', '来源详情', '来自IP', '总分', '您的姓名']
        
        answers = []
        
        for idx, row in df.iterrows():
            student_data = {
                'student_id': str(row.get('用户ID', f'user_{idx}')),
                'student_name': str(row.get('您的姓名', f'匿名_{idx}')),
                'submit_time': str(row.get('提交答卷时间', '')),
                'answers': {}
            }
            
            answer_cols = [col for col in df.columns if col not in meta_columns]
            
            for col_idx, col_name in enumerate(answer_cols, 1):
                answer_text = str(row.get(col_name, '')).strip()
                if answer_text and answer_text != 'nan':
                    answer_letter = self._extract_answer_letter(answer_text)
                    student_data['answers'][col_idx] = answer_letter or answer_text
            
            answers.append(student_data)
        
        print(f"✓ 加载了 {len(answers)} 名学员的答案")
        return answers
    
    def _extract_answer_letter(self, answer_text: str) -> str:
        """从答案文本中提取选项字母"""
        if not answer_text:
            return ''
        
        match = re.match(r'^([A-Z])[、．\s\.]', answer_text)
        if match:
            return match.group(1)
        
        if '、' in answer_text or ',' in answer_text:
            letters = re.findall(r'([A-Z])[、,．\s]', answer_text)
            if letters:
                return ''.join(letters)
        
        if answer_text in ['正确', 'A、正确', 'A.正确']:
            return 'A'
        if answer_text in ['错误', 'B、错误', 'B.错误']:
            return 'B'
        
        return answer_text
    
    def grade_objective_question(self, question: Dict, student_answer: str) -> Tuple[float, str]:
        """客观题评分 - 快速计算"""
        q_type = question['type']
        correct_answer = str(question.get('ans', '')).strip()
        student_answer = str(student_answer).strip()
        
        if q_type == '单选':
            if student_answer.upper() == correct_answer.upper():
                return 1.0, "✓ 正确"
            else:
                return 0.0, f"✗ 错误，正确答案: {correct_answer}"
        
        elif q_type == '判断':
            correct_normalized = self._normalize_judge(correct_answer)
            student_normalized = self._normalize_judge(student_answer)
            if student_normalized == correct_normalized:
                return 1.0, "✓ 正确"
            else:
                return 0.0, f"✗ 错误，正确答案: {correct_answer}"
        
        elif q_type == '多选':
            correct_ans = question.get('ans', [])
            if isinstance(correct_ans, list):
                correct_opts = set(a.upper() for a in correct_ans)
            else:
                correct_opts = set(re.findall(r'[A-Z]', str(correct_ans).upper()))
            
            student_opts = set(re.findall(r'[A-Z]', student_answer.upper()))
            
            if not correct_opts:
                return 0.0, "? 无法判断正确答案"
            
            correct_count = len(student_opts & correct_opts)
            wrong_count = len(student_opts - correct_opts)
            total_correct = len(correct_opts)
            
            if wrong_count > 0:
                score = 0.0
                comment = f"✗ 错误（含错误选项），正确答案: {correct_answer}"
            else:
                score = correct_count / total_correct
                if score == 1.0:
                    comment = "✓ 正确"
                else:
                    comment = f"~ 部分正确（漏选），正确答案: {correct_answer}"
            
            return score, comment
        
        elif q_type == '填空':
            return self._keyword_match(student_answer, correct_answer)
        
        else:
            return 0.0, "? 未知题型"
    
    def _normalize_judge(self, answer: str) -> str:
        """标准化判断题答案"""
        answer = answer.strip().lower()
        if answer in ['正确', '对', '是', 'true', 'yes', '√', '1', 'a']:
            return '正确'
        elif answer in ['错误', '错', '否', 'false', 'no', '×', '0', 'b']:
            return '错误'
        return answer
    
    def _keyword_match(self, student_answer: str, correct_answer: str) -> Tuple[float, str]:
        """关键词匹配评分"""
        if not student_answer or not correct_answer:
            return 0.0, "? 未作答"
        
        student_lower = student_answer.lower()
        correct_lower = correct_answer.lower()
        
        if student_answer == correct_answer:
            return 1.0, "✓ 正确"
        
        correct_keywords = set(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]{2,}', correct_lower))
        student_keywords = set(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]{2,}', student_lower))
        
        if not correct_keywords:
            return 0.0, "? 无法判断"
        
        matched = len(correct_keywords & student_keywords)
        score = matched / len(correct_keywords)
        
        if score >= 0.8:
            return 1.0, "✓ 正确"
        elif score >= 0.5:
            return score, f"~ 部分正确（{score:.0%}），参考答案: {correct_answer}"
        else:
            return 0.0, f"✗ 错误，参考答案: {correct_answer}"
    
    def grade_subjective_question_ollama(self, question: Dict, student_answer: str) -> Tuple[float, str]:
        """使用Ollama模型进行主观题语义评分"""
        correct_answer = question.get('explain', '') or question.get('ans', '')
        
        prompt = f"""你是一位专业的WM Caption培训评分老师，请对以下学员答案进行评分。

【题目】{question['q']}
【参考答案】{correct_answer}
【学员答案】{student_answer}

评分标准（满分100分）：
- 85-100分：答案完全正确，或核心概念表达准确
- 70-84分：答案基本正确，但不够完整或有轻微偏差
- 50-69分：答案部分正确，理解有一定偏差
- 0-49分：答案错误或与题目无关

请严格按照以下格式输出：
分数: [0-100的数字]
评语: [简要评价，说明得分原因]
"""
        
        try:
            response = self._call_ollama(prompt)
            score_match = re.search(r'分数[:：]?\s*(\d+)', response)
            
            if score_match:
                score = int(score_match.group(1)) / 100.0
            else:
                score = self._semantic_similarity(student_answer, correct_answer)
            
            comment_match = re.search(r'评语[:：]?\s*(.+?)(?:\n|$)', response, re.DOTALL)
            if comment_match:
                comment = comment_match.group(1).strip()
            else:
                comment = response[:200].replace('\n', ' ')
            
            return min(1.0, max(0.0, score)), comment
            
        except Exception as e:
            score = self._semantic_similarity(student_answer, correct_answer)
            return score, f"Ollama失败，相似度{score:.0%}"
    
    def _call_ollama(self, prompt: str) -> str:
        """调用Ollama API"""
        url = f"{self.ollama_url}/api/generate"
        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 300
            }
        }
        response = requests.post(url, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result.get('response', '')
    
    def _semantic_similarity(self, text1: str, text2: str) -> float:
        """计算文本语义相似度"""
        if not text1 or not text2:
            return 0.0
        
        similarity = SequenceMatcher(None, text1, text2).ratio()
        
        keywords1 = set(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]{2,}', text1.lower()))
        keywords2 = set(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]{2,}', text2.lower()))
        
        if keywords1 and keywords2:
            jaccard = len(keywords1 & keywords2) / len(keywords1 | keywords2) if (keywords1 | keywords2) else 0
            return (similarity * 0.3 + jaccard * 0.7)
        
        return similarity
    
    def grade_student_exam(self, exam_data: Dict, student_data: Dict, use_ollama: bool = True, 
                          student_idx: int = 0, total_students: int = 1) -> Dict:
        """为单个学生评分整张试卷 - 带详细进度"""
        student_answers = student_data['answers']
        questions = exam_data['questions']
        total_questions = len(questions)
        
        # 计算每题分值（根据总分和题目数量）
        self.score_per_question = self.total_score / total_questions
        
        # 统计需要Ollama评分的主观题数量
        subjective_count = sum(1 for q in questions if q['type'] in self.subjective_types)
        objective_count = total_questions - subjective_count
        
        results = {
            'student_id': student_data['student_id'],
            'student_name': student_data['student_name'],
            'submit_time': student_data.get('submit_time', ''),
            'graded_at': datetime.now().isoformat(),
            'total_score': 0,
            'max_score': 0,
            'percentage': 0,
            'questions': [],
            'summary': {}
        }
        
        student_header = f"[{student_idx}/{total_students}] {student_data['student_name']}"
        print(f"\n{'='*60}")
        print(f"开始评分: {student_header}")
        print(f"  总题数: {total_questions} | 客观题: {objective_count} | 主观题: {subjective_count}")
        print(f"{'='*60}")
        
        # 先处理客观题（快速）
        objective_correct = 0
        for idx, question in enumerate(questions, 1):
            q_type = question['type']
            if q_type in self.subjective_types:
                continue  # 跳过主观题，后面处理
                
            student_answer = student_answers.get(idx, '')
            score, comment = self.grade_objective_question(question, student_answer)
            
            # 计算实际得分（按每题分值）
            actual_score = score * self.score_per_question
            
            q_result = {
                'question_num': idx,
                'question_id': question['id'],
                'type': q_type,
                'difficulty': question['difficulty'],
                'student_answer': student_answer,
                'correct_answer': question.get('ans', ''),
                'score_rate': round(score, 2),           # 得分率 0-1
                'score': round(actual_score, 2),         # 实际得分
                'max_score': round(self.score_per_question, 2),  # 该题满分
                'comment': comment
            }
            results['questions'].append(q_result)
            results['total_score'] += actual_score
            results['max_score'] += self.score_per_question
            
            if score >= 0.9:
                objective_correct += 1
        
        if objective_count > 0:
            print(f"  ✓ 客观题完成: {objective_correct}/{objective_count} 正确")
        
        # 处理主观题（显示详细进度）
        if subjective_count > 0 and use_ollama:
            print(f"\n  ▶ 开始主观题评分 (调用Ollama，请稍候)...")
            subjective_idx = 0
            
            for idx, question in enumerate(questions, 1):
                q_type = question['type']
                if q_type not in self.subjective_types:
                    continue
                    
                subjective_idx += 1
                student_answer = student_answers.get(idx, '')
                
                # 显示进度条
                prefix = f"  主观题 [{subjective_idx}/{subjective_count}]"
                suffix = f"题号{idx} | {q_type}"
                print_progress_bar(subjective_idx - 1, subjective_count, prefix, suffix, length=30)
                
                score, comment = self.grade_subjective_question_ollama(question, student_answer)
                
                # 计算实际得分（按每题分值）
                actual_score = score * self.score_per_question
                
                q_result = {
                    'question_num': idx,
                    'question_id': question['id'],
                    'type': q_type,
                    'difficulty': question['difficulty'],
                    'student_answer': student_answer,
                    'correct_answer': question.get('ans', ''),
                    'score_rate': round(score, 2),
                    'score': round(actual_score, 2),
                    'max_score': round(self.score_per_question, 2),
                    'comment': comment
                }
                results['questions'].append(q_result)
                results['total_score'] += actual_score
                results['max_score'] += self.score_per_question
            
            # 完成最后一步
            print_progress_bar(subjective_count, subjective_count, prefix, "完成", length=30)
        
        # 排序题号
        results['questions'].sort(key=lambda x: x['question_num'])
        
        if results['max_score'] > 0:
            results['percentage'] = round(results['total_score'] / results['max_score'] * 100, 1)
        
        results['summary'] = self._generate_summary(results['questions'])
        
        print(f"\n  ✓ {student_data['student_name']} 评分完成: {results['total_score']:.2f}/{results['max_score']} ({results['percentage']}%)")
        
        return results
    
    def _generate_summary(self, question_results: List[Dict]) -> Dict:
        """生成评分摘要"""
        summary = {
            'total_questions': len(question_results),
            'correct_count': sum(1 for q in question_results if q['score_rate'] >= 0.9),
            'partial_count': sum(1 for q in question_results if 0.5 <= q['score_rate'] < 0.9),
            'wrong_count': sum(1 for q in question_results if q['score_rate'] < 0.5),
            'type_scores': {},
            'difficulty_scores': {}
        }
        
        type_stats = {}
        for q in question_results:
            q_type = q['type']
            if q_type not in type_stats:
                type_stats[q_type] = {'total': 0, 'count': 0}
            type_stats[q_type]['total'] += q['score']
            type_stats[q_type]['count'] += 1
        
        for t, data in type_stats.items():
            summary['type_scores'][t] = round(data['total'] / data['count'], 2)
        
        diff_stats = {}
        for q in question_results:
            diff = q['difficulty']
            if diff not in diff_stats:
                diff_stats[diff] = {'total': 0, 'count': 0}
            diff_stats[diff]['total'] += q['score']
            diff_stats[diff]['count'] += 1
        
        for d, data in diff_stats.items():
            summary['difficulty_scores'][f'{"★"*d}'] = round(data['total'] / data['count'], 2)
        
        return summary
    
    def export_summary_csv(self, all_results: List[Dict], output_dir: str, exam_data: Dict) -> str:
        """导出汇总CSV表格：姓名|得分|需关注|题1|题2|...|题40"""
        os.makedirs(output_dir, exist_ok=True)
        
        # 获取题目数量
        total_questions = len(exam_data['questions'])
        
        # 构建表头
        header = ['姓名', '得分', '需关注(<60%)'] + [f'题{i}' for i in range(1, total_questions + 1)]
        
        csv_path = os.path.join(output_dir, f"成绩汇总表_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            
            for result in all_results:
                # 按题号排序，确保顺序正确
                questions_sorted = sorted(result['questions'], key=lambda x: x['question_num'])
                
                # 提取每道题的学生答案
                answers = [q['student_answer'] for q in questions_sorted]
                
                # 是否需要关注（低于60%）
                need_attention = "是" if result['percentage'] < 60 else "否"
                
                row = [
                    result['student_name'],
                    f"{result['total_score']:.2f}",
                    need_attention
                ] + answers
                
                writer.writerow(row)
        
        return csv_path


def check_ollama_available(url: str) -> bool:
    """检查Ollama服务是否可用"""
    try:
        response = requests.get(f"{url}/api/tags", timeout=5)
        return response.status_code == 200
    except:
        return False


def main():
    """主函数"""
    # ==================== 路径配置区域 ====================
    # 1. 答题结果Excel（问卷星下载的）
    ANSWER_EXCEL_PATH = os.path.join(ROOT_DIR, 'data', 'answer', '367793615_按文本_WM内部评估_2_2.xlsx')
    
    # 2. 考试JSON文件（组卷后生成的试卷JSON）
    EXAM_JSON_PATH = os.path.join(ROOT_DIR, 'data', 'exer', 'WMCaption考试_20260609_135613.json')
    
    # 3. 评分结果输出目录
    OUTPUT_DIR = os.path.join(ROOT_DIR, 'data', 'outputbyollama')
    
    # 4. Ollama服务地址
    OLLAMA_URL = "http://localhost:11434"
    
    # 5. 是否禁用Ollama
    DISABLE_OLLAMA = False
    
    # 6. 考试总分（问卷星设置的满分，默认50分）
    EXAM_TOTAL_SCORE = 50
    # ==================== 配置结束 ====================
    
    # 检查文件
    if not os.path.exists(EXAM_JSON_PATH):
        print(f"✗ 错误: 找不到考试文件 {EXAM_JSON_PATH}")
        print("  提示: 这是组卷后生成的40题试卷JSON，不是完整题库")
        return
    
    if not os.path.exists(ANSWER_EXCEL_PATH):
        print(f"✗ 错误: 找不到答案文件 {ANSWER_EXCEL_PATH}")
        return
    
    # 创建评分系统（传入考试总分）
    grader = GradingSystem(ollama_url=OLLAMA_URL, total_score=EXAM_TOTAL_SCORE)
    
    # 加载考试文件（40题的试卷）
    print(f"\n加载考试文件: {EXAM_JSON_PATH}")
    exam_data = grader.load_exam_data(EXAM_JSON_PATH)
    print(f"  共 {len(exam_data['questions'])} 题，满分 {EXAM_TOTAL_SCORE} 分")
    
    # 统计题型
    type_count = {}
    for q in exam_data['questions']:
        q_type = q['type']
        type_count[q_type] = type_count.get(q_type, 0) + 1
    print("  题型分布:", ", ".join([f"{k}:{v}" for k, v in type_count.items()]))
    
    grader.build_question_map_from_exam(exam_data)
    
    # 加载答案
    print(f"\n加载答案: {ANSWER_EXCEL_PATH}")
    students_data = grader.load_answers_from_wjx_excel(ANSWER_EXCEL_PATH)
    
    if not students_data:
        print("✗ 未能加载任何答案")
        return
    
    # 检查Ollama
    use_ollama = not DISABLE_OLLAMA and check_ollama_available(OLLAMA_URL)
    if use_ollama:
        print("✓ Ollama服务已连接")
    else:
        print("⚠ Ollama服务不可用，使用文本相似度评分")
    
    # 评分
    print(f"\n{'='*60}")
    print("开始批量评分...")
    print(f"{'='*60}")
    
    all_results = []
    total_students = len(students_data)
    
    for i, student in enumerate(students_data, 1):
        result = grader.grade_student_exam(
            exam_data, student, 
            use_ollama=use_ollama,
            student_idx=i,
            total_students=total_students
        )
        all_results.append(result)
    
    # 最终汇总
    all_results.sort(key=lambda x: x['percentage'], reverse=True)
    print(f"\n{'='*60}")
    print("评分完成！成绩汇总")
    print(f"{'='*60}")
    print(f"\n{'排名':<4} {'姓名':<12} {'得分':<8} {'状态'}")
    print("-" * 40)
    for i, r in enumerate(all_results, 1):
        status = "✓ 通过" if r['percentage'] >= 60 else "✗ 需关注"
        print(f"{i:<4} {r['student_name']:<12} {r['total_score']:<8.2f} {status}")
    
    # 导出汇总CSV表（唯一输出文件）
    summary_csv_path = grader.export_summary_csv(all_results, OUTPUT_DIR, exam_data)
    
    print(f"\n{'='*60}")
    print(f"✓ 汇总表格已保存: {summary_csv_path}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
