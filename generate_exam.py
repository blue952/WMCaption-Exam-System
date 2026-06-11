#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
World Model Caption 智能组题系统
支持权重配置、难度配比、去重机制
"""

import json
import random
import os
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HISTORY_PATH = os.path.join(ROOT_DIR, 'exam_history.json')
DEFAULT_BANK_PATH = os.path.join(ROOT_DIR, 'data', 'test', 'WMCaption_题库_v2.json')
DEFAULT_OUTPUT_DIR = os.path.join(ROOT_DIR, 'data', 'exer')


class ExamGenerator:
    """试卷生成器"""
    
    # 默认组题策略配置
    DEFAULT_CONFIG = {
        'total_questions': 40,  # 总题数
        'total_score': 100,     # 总分改为100
        'difficulty_ratio': {   # 难度配比
            1: 0.30,  # 简单 30%
            2: 0.55,  # 中等 55%
            3: 0.15   # 困难 15%
        },
        'type_ratio': {         # 题型配比
            '单选': 16,       # 单选16题
            '判断': 11,        # 判断11题
            '多选': 7,      # 多选7题
            '填空': 3,          # 填空3题
            '情景': 2,      # 情景2题（主观）
            '综合': 1   # 综合1题（主观）
        },
        'chapter_weights': {    # 章节权重配置
            'A': 4,   # 定义与哲学
            'B': 4,   # 拓扑方位
            'C': 3,   # 没有相机
            'D': 2,   # MM平台
            'E': 2,   # Global总览
            'F': 2,   # style
            'G': 2,   # lighting
            'H': 2,   # atmosphere
            'I': 2,   # screen
            'J': 2,   # init_camera
            'K': 1,   # Global其他
            'L': 1,   # Entities定义
            'M': 1,   # Subject
            'N': 1,   # Object交互
            'O': 1,   # Object密度
            'P': 1,   # Object锚点
            'Q': 1,   # Object群组
            'R': 1,   # Offscreen
            'S': 1,   # Events总览
            'T': 1,   # world_action
            'U': 1,   # screen_change
            'V': 1,   # audio
            'W': 1,   # lighting_change
            'X': 1,   # atmosphere_change
            'Y': 1,   # style_change
            'Z': 1,   # view_change
            'AA': 5,  # 字段归属（重点）
            'AB': 2,  # 情景分析
            'AC': 2,  # 错误修正
            'AD': 2   # 综合应用
        }
    }
    
    def __init__(self, question_bank_path: str, history_path: str = DEFAULT_HISTORY_PATH):
        self.question_bank_path = question_bank_path
        self.history_path = history_path
        self.questions = []
        self.history = {}
        self.config = self.DEFAULT_CONFIG.copy()
        
        self._load_question_bank()
        self._load_history()
    
    def _load_question_bank(self):
        """加载题库"""
        with open(self.question_bank_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.questions = data['questions']
        print(f"✓ 题库加载完成，共 {len(self.questions)} 题")
        
        # 统计题型分布
        type_count = defaultdict(int)
        for q in self.questions:
            type_count[q['type']] += 1
        print(f"  题型分布: {dict(type_count)}")
    
    def _load_history(self):
        """加载历史记录"""
        if os.path.exists(self.history_path):
            with open(self.history_path, 'r', encoding='utf-8') as f:
                self.history = json.load(f)
        else:
            self.history = {'used_questions': [], 'exam_records': []}
    
    def _save_history(self):
        """保存历史记录"""
        with open(self.history_path, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
    
    def generate_exam(self, exam_name: str = None, exclude_recent: int = 10) -> Dict:
        """
        生成试卷
        
        Args:
            exam_name: 试卷名称
            exclude_recent: 排除最近N次考试已使用的题目
        """
        if exam_name is None:
            exam_name = f"WMCaption考试_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 获取需要排除的题目ID
        excluded_ids = self._get_excluded_ids(exclude_recent)
        
        # 按题型分组
        questions_by_type = defaultdict(list)
        for q in self.questions:
            if q['id'] not in excluded_ids:
                questions_by_type[q['type']].append(q)
        
        selected_questions = []
        
        # 按题型配比抽题
        for q_type, count in self.config['type_ratio'].items():
            available = questions_by_type.get(q_type, [])
            if len(available) < count:
                print(f"⚠ 警告: {q_type} 类型题目不足，需要{count}题，只有{len(available)}题")
                count = len(available)
            
            # 按章节权重进行分层抽样
            selected = self._weighted_sample(available, count)
            selected_questions.extend(selected)
        
        # 打乱顺序
        random.shuffle(selected_questions)
        
        # 生成试卷
        exam = {
            'exam_name': exam_name,
            'created_at': datetime.now().isoformat(),
            'total_questions': len(selected_questions),
            'config': self.config,
            'questions': selected_questions
        }
        
        # 记录历史
        self._record_exam(exam)
        
        return exam
    
    def _get_excluded_ids(self, recent_count: int) -> set:
        """获取需要排除的题目ID"""
        excluded = set()
        
        # 如果只排除最近的N次考试
        if recent_count > 0:
            records = self.history.get('exam_records', [])
            recent_records = records[-recent_count:]
            for record in recent_records:
                excluded.update(record.get('question_ids', []))
        else:
            # 排除所有已使用过的题目
            excluded.update(self.history.get('used_questions', []))
        
        return excluded
    
    def _weighted_sample(self, questions: List[Dict], count: int) -> List[Dict]:
        """
        按章节权重进行分层抽样
        """
        # 按章节分组
        by_chapter = defaultdict(list)
        for q in questions:
            by_chapter[q['section']].append(q)
        
        selected = []
        remaining = count
        
        # 计算总权重
        total_weight = sum(
            self.config['chapter_weights'].get(chap, 1) * len(qs)
            for chap, qs in by_chapter.items()
        )
        
        # 按权重比例从各章节抽样
        for chap, qs in sorted(by_chapter.items(), key=lambda x: -self.config['chapter_weights'].get(x[0], 1)):
            if remaining <= 0:
                break
            
            weight = self.config['chapter_weights'].get(chap, 1)
            # 计算该章节应抽题目数
            if total_weight > 0:
                target = max(1, int(count * weight * len(qs) / total_weight))
            else:
                target = 1
            
            sample_count = min(target, len(qs), remaining)
            if sample_count > 0:
                samples = random.sample(qs, sample_count)
                selected.extend(samples)
                remaining -= sample_count
        
        # 如果还有剩余名额，随机补充
        if remaining > 0:
            remaining_questions = [q for q in questions if q not in selected]
            if remaining_questions:
                additional = random.sample(remaining_questions, min(remaining, len(remaining_questions)))
                selected.extend(additional)
        
        return selected[:count]
    
    def _record_exam(self, exam: Dict):
        """记录考试历史"""
        # 添加到已使用题目
        for q in exam['questions']:
            if q['id'] not in self.history['used_questions']:
                self.history['used_questions'].append(q['id'])
        
        # 简化记录（只存ID和基本信息）
        exam_record = {
            'exam_name': exam['exam_name'],
            'created_at': exam['created_at'],
            'total_questions': exam['total_questions'],
            'question_ids': [q['id'] for q in exam['questions']]
        }
        
        self.history['exam_records'].append(exam_record)
        self._save_history()
    
    def export_for_feishu(self, exam: Dict, output_dir: str = os.path.join(ROOT_DIR, 'feishu_export')) -> tuple:
        """
        导出为飞书多维表格导入格式（CSV）
        生成两个文件：试卷.csv + 答案.csv
        
        Returns:
            (试卷路径, 答案路径)
        """
        import csv
        
        os.makedirs(output_dir, exist_ok=True)
        
        # 试卷文件（不含答案）
        exam_file = os.path.join(output_dir, f"{exam['exam_name']}_试卷.csv")
        with open(exam_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['题号', '题型', '难度', '章节', '题目内容', '选项A', '选项B', '选项C', '选项D', '作答区'])
            
            for idx, q in enumerate(exam['questions'], 1):
                options = q.get('opts') or []
                opt_texts = ['', '', '', '']
                for i, opt in enumerate(options[:4]):
                    if isinstance(opt, str):
                        # 去除选项前缀如 "A. "
                        opt_clean = opt.strip()
                        if len(opt_clean) > 2 and opt_clean[1] in ['.', '．', ' ']:
                            opt_clean = opt_clean[2:].strip()
                        opt_texts[i] = opt_clean
                    else:
                        opt_texts[i] = str(opt)
                
                writer.writerow([
                    idx,
                    q['type'],
                    '★' * q['difficulty'],
                    q['section'],
                    q['q'],
                    opt_texts[0],
                    opt_texts[1],
                    opt_texts[2],
                    opt_texts[3],
                    ''  # 作答区空白
                ])
        
        # 答案文件
        answer_file = os.path.join(output_dir, f"{exam['exam_name']}_答案.csv")
        with open(answer_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['题号', '原题ID', '题型', '难度', '正确答案', '解析'])
            
            for idx, q in enumerate(exam['questions'], 1):
                ans = q.get('ans', '')
                if isinstance(ans, list):
                    ans = ','.join(ans)
                writer.writerow([
                    idx,
                    q['id'],
                    q['type'],
                    '★' * q['difficulty'],
                    ans,
                    q.get('explain', '')
                ])
        
        print(f"✓ 试卷已导出: {exam_file}")
        print(f"✓ 答案已导出: {answer_file}")
        
        return exam_file, answer_file
    
    def print_exam_summary(self, exam: Dict):
        """打印试卷摘要"""
        print(f"\n{'='*60}")
        print(f"试卷名称: {exam['exam_name']}")
        print(f"生成时间: {exam['created_at']}")
        print(f"总题数: {exam['total_questions']}")
        print(f"总分: {self.config['total_score']}分")
        print(f"{'='*60}")
        
        # 统计
        type_count = defaultdict(int)
        diff_count = defaultdict(int)
        chapter_count = defaultdict(int)
        
        for q in exam['questions']:
            type_count[q['type']] += 1
            diff_count[q['difficulty']] += 1
            chapter_count[q['section']] += 1
        
        print("\n题型分布:")
        for t, c in sorted(type_count.items()):
            print(f"  {t}: {c}题")
        
        print("\n难度分布:")
        for d in sorted(diff_count.keys()):
            c = diff_count[d]
            stars = '★' * d
            print(f"  {stars}: {c}题")
        
        print(f"\n覆盖章节: {len(chapter_count)}个")
        print(f"  章节: {', '.join(sorted(chapter_count.keys()))}")
    
    def export_for_wenjuanxing(self, exam: Dict, output_dir: str = DEFAULT_OUTPUT_DIR, file_format: str = 'csv') -> str:
        """
        导出为问卷星/腾讯问卷兼容格式
        支持CSV和Excel两种格式
        """
        import csv
        
        os.makedirs(output_dir, exist_ok=True)
        
        # 计算每题分值（支持小数）
        total_score = self.config.get('total_score', 100)  # 默认100分
        question_count = len(exam['questions'])
        score_per_question = round(total_score / question_count, 2)
        
        # 准备数据 - 使用问卷星标准表头
        rows = []
        rows.append(['题型', '题目', '选项1', '选项2', '选项3', '选项4', '选项5', '正确答案', '答案解析', '分值'])
        
        # 添加姓名收集题（作为第1题）
        rows.append(['填空题', '您的姓名', '', '', '', '', '', '', '', '0'])
        
        for q in exam['questions']:
            q_type = q['type']
            
            # 转换题型编码
            if q_type == '单选':
                type_code = '单选题'
            elif q_type == '多选':
                type_code = '多选题'
            elif q_type == '判断':
                type_code = '判断题'
            elif q_type == '填空':
                type_code = '填空题'
            else:
                type_code = '简答题'
            
            # 处理选项 - 保留原始前缀如 "A、"
            options = q.get('opts') or []
            opt_texts = ['', '', '', '', '']
            for i, opt in enumerate(options[:5]):
                if isinstance(opt, str):
                    opt_texts[i] = opt.strip()
                else:
                    opt_texts[i] = str(opt)
            
            # 处理答案
            ans = q.get('ans', '')
            if isinstance(ans, list):
                ans = ''.join(ans)
            
            # 判断题选项固定为问卷星格式
            if q_type == '判断':
                opt_texts[0] = 'A、正确'
                opt_texts[1] = 'B、错误'
                opt_texts[2] = ''
                opt_texts[3] = ''
                opt_texts[4] = ''
                if ans in ['正确', '对', '是', 'T', 'True', 'true', 'A']:
                    ans = 'A'
                elif ans in ['错误', '错', '否', 'F', 'False', 'false', 'B']:
                    ans = 'B'
            
            rows.append([
                type_code,
                q['q'],
                opt_texts[0],
                opt_texts[1],
                opt_texts[2],
                opt_texts[3],
                opt_texts[4],
                ans,
                q.get('explain', ''),
                str(score_per_question)
            ])
        
        # 根据格式导出
        if file_format.lower() == 'excel':
            try:
                from openpyxl import Workbook
                output_file = os.path.join(output_dir, f"{exam['exam_name']}_问卷星导入.xlsx")
                wb = Workbook()
                ws = wb.active
                ws.title = "题目"
                for row in rows:
                    ws.append(row)
                wb.save(output_file)
                print(f"✓ 问卷星Excel格式已导出: {output_file}")
            except ImportError:
                print("⚠ 未安装openpyxl，已转为CSV格式")
                file_format = 'csv'
        
        if file_format.lower() == 'csv':
            output_file = os.path.join(output_dir, f"{exam['exam_name']}_问卷星导入.csv")
            with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerows(rows)
            print(f"✓ 问卷星CSV格式已导出: {output_file}")
        
        print("  使用说明:")
        print("  1. 访问 https://www.wjx.cn 或 https://wj.qq.com")
        print("  2. 创建新问卷 → 选择'考试'类型")
        print("  3. 点击'导入题目' → 选择此文件")
        print("  4. 系统自动识别题型、选项和正确答案")
        
        return output_file


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='WMCaption 智能组题系统')
    parser.add_argument('--bank', '-b', default=DEFAULT_BANK_PATH, help='题库JSON路径')
    parser.add_argument('--name', '-n', default=None, help='试卷名称')
    parser.add_argument('--exclude', '-e', type=int, default=10, help='排除最近N次考试的题目')
    parser.add_argument('--output', '-o', default=DEFAULT_OUTPUT_DIR, help='输出目录')
    
    args = parser.parse_args()
    
    # 检查题库文件
    if not os.path.exists(args.bank):
        print(f"✗ 错误: 找不到题库文件 {args.bank}")
        print("请确保JSON题库文件存在")
        return
    
    # 创建生成器
    generator = ExamGenerator(args.bank)
    
    # 生成试卷
    print("\n正在生成试卷...")
    exam = generator.generate_exam(exam_name=args.name, exclude_recent=args.exclude)
    
    # 打印摘要
    generator.print_exam_summary(exam)
    
    # 交互式选择导出格式
    print(f"\n{'='*60}")
    print("请选择导出格式:")
    print("  1. 飞书多维表格格式 (CSV)")
    print("  2. 问卷星/腾讯问卷导入格式 (CSV)")
    print("  3. 全部格式")
    print(f"{'='*60}")
    
    while True:
        choice = input("请输入选项 (1/2/3): ").strip()
        if choice in ['1', '2', '3']:
            break
        print("无效选项，请重新输入")
    
    # 根据选择导出
    if choice in ['1', '3']:
        exam_file, answer_file = generator.export_for_feishu(exam, args.output)
    
    if choice in ['2', '3']:
        print("  1. CSV格式")
        print("  2. Excel格式")
        fmt_choice = input("请输入选项 (1/2): ").strip()
        fmt = 'excel' if fmt_choice == '2' else 'csv'
        wjx_file = generator.export_for_wenjuanxing(exam, args.output, file_format=fmt)
    
    # 同时保存JSON格式
    exam_json = os.path.join(args.output, f"{exam['exam_name']}.json")
    with open(exam_json, 'w', encoding='utf-8') as f:
        json.dump(exam, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 试卷JSON已保存: {exam_json}")
    
    print(f"\n{'='*60}")
    print("使用说明:")
    if choice in ['1', '3']:
        print(f"[飞书多维表格]")
        print(f"  1. 将试卷CSV导入飞书多维表格")
        print(f"  2. 创建表单供学员答题")
        print(f"  3. 答题完成后导出答案CSV")
        print(f"  4. 使用 grading_system.py 进行自动评分")
    if choice in ['2', '3']:
        print(f"\n[问卷星/腾讯问卷]")
        print(f"  1. 访问 wjx.cn 或 wj.qq.com 创建考试")
        print(f"  2. 导入生成的CSV文件批量添加题目")
        print(f"  3. 发布问卷让学员答题")
        print(f"  4. 导出答案后用 grading_system.py 评分")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
