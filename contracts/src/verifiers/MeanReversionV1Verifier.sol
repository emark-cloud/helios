// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract MeanReversionV1Verifier {
    // Scalar field size
    uint256 constant r =
        21_888_242_871_839_275_222_246_405_745_257_275_088_548_364_400_416_034_343_698_204_186_575_808_495_617;
    // Base field size
    uint256 constant q =
        21_888_242_871_839_275_222_246_405_745_257_275_088_696_311_157_297_823_662_689_037_894_645_226_208_583;

    // Verification Key data
    uint256 constant alphax =
        20_491_192_805_390_485_299_153_009_773_594_534_940_189_261_866_228_447_918_068_658_471_970_481_763_042;
    uint256 constant alphay =
        9_383_485_363_053_290_200_918_347_156_157_836_566_562_967_994_039_712_273_449_902_621_266_178_545_958;
    uint256 constant betax1 =
        4_252_822_878_758_300_859_123_897_981_450_591_353_533_073_413_197_771_768_651_442_665_752_259_397_132;
    uint256 constant betax2 =
        6_375_614_351_688_725_206_403_948_262_868_962_793_625_744_043_794_305_715_222_011_528_459_656_738_731;
    uint256 constant betay1 =
        21_847_035_105_528_745_403_288_232_691_147_584_728_191_162_732_299_865_338_377_159_692_350_059_136_679;
    uint256 constant betay2 =
        10_505_242_626_370_262_277_552_901_082_094_356_697_409_835_680_220_590_971_873_171_140_371_331_206_856;
    uint256 constant gammax1 =
        11_559_732_032_986_387_107_991_004_021_392_285_783_925_812_861_821_192_530_917_403_151_452_391_805_634;
    uint256 constant gammax2 =
        10_857_046_999_023_057_135_944_570_762_232_829_481_370_756_359_578_518_086_990_519_993_285_655_852_781;
    uint256 constant gammay1 =
        4_082_367_875_863_433_681_332_203_403_145_435_568_316_851_327_593_401_208_105_741_076_214_120_093_531;
    uint256 constant gammay2 =
        8_495_653_923_123_431_417_604_973_247_489_272_438_418_190_587_263_600_148_770_280_649_306_958_101_930;
    uint256 constant deltax1 =
        20_775_743_520_368_889_094_666_957_188_441_834_368_060_055_319_599_829_176_711_126_921_134_090_032_774;
    uint256 constant deltax2 =
        17_198_060_243_927_569_523_272_001_941_987_063_654_321_355_178_918_445_089_362_929_245_533_351_643_306;
    uint256 constant deltay1 =
        3_985_250_719_174_073_025_455_661_301_373_693_160_774_704_173_579_555_190_330_479_133_080_455_001_825;
    uint256 constant deltay2 =
        16_559_843_652_474_967_595_953_104_861_115_358_101_789_551_082_070_615_809_793_823_475_013_243_982_660;

    uint256 constant IC0x =
        4_331_199_385_114_473_495_732_130_067_892_841_208_146_506_810_060_408_067_536_303_572_698_045_334_517;
    uint256 constant IC0y =
        14_731_160_261_632_009_297_941_301_110_861_341_773_855_326_971_738_916_891_981_859_364_149_653_393_786;

    uint256 constant IC1x =
        17_427_764_922_963_369_207_426_032_571_670_147_611_466_896_589_579_442_068_006_115_875_308_420_779_013;
    uint256 constant IC1y =
        13_751_657_084_109_947_830_817_861_774_914_689_561_032_163_628_038_093_054_606_580_866_734_685_103_414;

    uint256 constant IC2x =
        20_823_398_137_951_977_390_726_228_051_024_510_872_439_205_530_270_068_286_864_842_977_583_588_728_087;
    uint256 constant IC2y =
        17_880_103_565_609_099_282_280_007_722_686_383_805_668_029_284_575_019_157_971_105_483_419_148_558_893;

    uint256 constant IC3x =
        412_250_856_127_758_175_491_523_898_322_343_051_653_300_972_624_235_455_888_256_869_465_310_548_696;
    uint256 constant IC3y =
        15_337_239_835_149_711_355_445_109_568_311_940_274_077_959_393_718_935_280_004_068_197_739_030_685_039;

    uint256 constant IC4x =
        13_676_302_763_736_601_047_601_152_160_015_649_242_646_954_449_222_005_398_455_815_356_190_470_469_450;
    uint256 constant IC4y =
        19_650_227_009_986_904_497_784_674_513_594_370_334_154_443_080_469_193_115_367_111_853_821_117_878_660;

    uint256 constant IC5x =
        14_320_697_046_214_942_876_783_672_560_208_293_960_728_493_820_481_851_817_981_806_174_102_721_942_265;
    uint256 constant IC5y =
        5_866_078_352_630_084_844_250_621_546_237_640_658_001_931_580_780_345_264_401_089_532_223_734_697_391;

    uint256 constant IC6x =
        211_594_053_541_600_431_625_303_227_416_497_298_725_926_017_002_491_895_731_456_593_676_110_870_983;
    uint256 constant IC6y =
        2_115_809_785_477_118_823_600_306_364_137_641_229_215_091_012_845_839_987_785_379_260_096_584_406_044;

    uint256 constant IC7x =
        12_538_891_894_282_077_349_487_479_196_919_435_205_895_437_310_872_142_552_936_137_944_337_690_207_047;
    uint256 constant IC7y =
        2_833_350_448_077_695_142_514_357_452_436_414_524_707_591_925_270_282_215_776_638_489_969_688_292_689;

    uint256 constant IC8x =
        14_392_725_842_193_631_577_854_498_021_344_177_665_778_649_829_556_137_019_015_788_278_735_468_753_089;
    uint256 constant IC8y =
        8_797_513_907_430_609_843_803_917_041_403_006_885_704_845_057_756_593_188_350_719_247_124_063_804_990;

    uint256 constant IC9x =
        8_516_795_080_542_657_545_057_585_832_260_558_373_321_543_297_598_129_348_683_955_829_816_771_427_009;
    uint256 constant IC9y =
        14_903_955_196_265_429_045_317_486_147_174_706_080_210_096_510_153_515_433_650_350_681_845_899_724_075;

    uint256 constant IC10x =
        12_480_474_116_136_883_824_697_812_363_683_607_716_109_601_284_043_551_575_127_625_841_651_239_586_567;
    uint256 constant IC10y =
        19_001_770_759_078_941_173_644_628_821_551_839_373_755_511_056_947_019_882_685_715_466_242_309_620_635;

    uint256 constant IC11x =
        6_033_640_480_238_412_551_152_047_845_253_483_016_102_507_129_583_562_830_398_953_081_957_324_299_595;
    uint256 constant IC11y =
        3_552_458_412_585_413_027_564_267_231_284_101_480_289_396_700_369_954_798_168_171_141_078_749_788_542;

    uint256 constant IC12x =
        1_049_976_424_518_795_729_885_793_637_324_073_289_774_874_102_957_137_654_590_878_821_856_089_697_827;
    uint256 constant IC12y =
        6_963_261_752_383_542_487_594_296_736_042_699_169_650_028_457_915_308_427_688_136_778_161_719_753_280;

    uint256 constant IC13x =
        13_102_833_271_916_422_124_647_527_670_432_620_659_075_707_156_982_904_181_518_127_620_432_245_779_091;
    uint256 constant IC13y =
        165_273_664_964_339_080_221_945_794_514_229_538_274_881_504_696_129_728_771_340_326_846_979_668_171;

    uint256 constant IC14x =
        7_318_611_502_849_580_448_872_583_300_975_670_526_231_182_624_749_062_446_105_317_786_339_032_868_270;
    uint256 constant IC14y =
        13_015_573_411_409_980_864_527_072_689_571_469_067_860_492_274_197_082_322_268_548_851_373_869_487_025;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[14] calldata _pubSignals
    ) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x

                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))

                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))

                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))

                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))

                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))

                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))

                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))

                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))

                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))

                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))

                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))

                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))

                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))

                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))

                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)

                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F

            checkField(calldataload(add(_pubSignals, 0)))

            checkField(calldataload(add(_pubSignals, 32)))

            checkField(calldataload(add(_pubSignals, 64)))

            checkField(calldataload(add(_pubSignals, 96)))

            checkField(calldataload(add(_pubSignals, 128)))

            checkField(calldataload(add(_pubSignals, 160)))

            checkField(calldataload(add(_pubSignals, 192)))

            checkField(calldataload(add(_pubSignals, 224)))

            checkField(calldataload(add(_pubSignals, 256)))

            checkField(calldataload(add(_pubSignals, 288)))

            checkField(calldataload(add(_pubSignals, 320)))

            checkField(calldataload(add(_pubSignals, 352)))

            checkField(calldataload(add(_pubSignals, 384)))

            checkField(calldataload(add(_pubSignals, 416)))

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
